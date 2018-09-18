from scrapy.spider import BaseSpider
from scrapy.selector import HtmlXPathSelector
from scrapy.http import Request
from scrapy.http import TextResponse
from scrapy.http import Response
from scrapy.exceptions import CloseSpider
from search.items import SearchItem
from search.spiders.search_spider import SearchSpider
from scrapy import log

from spiders_utils import Utils
from search.matching_utils import ProcessText

import re
import sys


class TargetSpider(SearchSpider):

	name = "target"

	# initialize fields specific to this derived spider
	def init_sub(self):
		self.target_site = "target"
		self.start_urls = [ "http://www.target.com" ]

	# # try to find product name using its page URL and the name extracted from results page (usually incomplete)
	# def build_product_name(results_name, URL):
	# 	pass


	# create product items from results using only results pages (extracting needed info on products from there)
	# parse results page for target, extract info for all products returned by search (keep them in "meta")
	def parseResults(self, response):
		hxs = HtmlXPathSelector(response)

		if 'items' in response.meta:
			items = response.meta['items']
		else:
			items = set()

		#results = hxs.select("//ul[@class='productsListView']/li")
		results = hxs.select("//li[contains(@class,'tile standard')]")
		for result in results:
			item = SearchItem()
			product_title_holder = result.select(".//div[@class='tileInfo']/a[contains(@class,'productTitle')]")
			product_url = product_title_holder.select("@href").extract()
			product_name = product_title_holder.select("@title").extract()

			#print "ITEM", product_name

			# quit if there is no product name
			if product_name and product_url:
				# clean url
				m = re.match("(.*)#prodSlot*",url.extract(), product_url[0])
				if m:
					item['product_url'] = m.group(1)
				else:
					item['product_url'] = product_url[0]
				item['product_name'] = product_name[0]
			else:
				self.log("No product name: " + str(response.url) + " from product: " + response.meta['origin_url'], level=log.ERROR)
				continue

			# add url, name and model of product to be matched (from origin site)
			item['origin_url'] = response.meta['origin_url']
			item['origin_name'] = response.meta['origin_name']

			if 'origin_model' in response.meta:
				item['origin_model'] = response.meta['origin_model']

			# extract product model from name
			product_model_extracted = ProcessText.extract_model_from_name(item['product_name'])
			if product_model_extracted:
				item['product_model'] = product_model_extracted

			# extract price
			#! extracting regular price and not discount price when discounts available?
			price_holder = result.select(".//p[@class='regularprice-label']//text()[contains(.,'$')]").extract()

			# second attempt at finding price
			if not price_holder:
				price_holder = result.select(".//*[contains(@class, 'price price-label')]/text()[contains(.,'$')]").extract()

			if price_holder:
				product_target_price = price_holder[0].strip()
				# remove commas separating orders of magnitude (ex 2,000)
				product_target_price = re.sub(",","",product_target_price)
				# if more than one match, it will get the first one
				m = re.match("\$([0-9]+\.?[0-9]*)", product_target_price)
				if m:
					item['product_target_price'] = float(m.group(1))
				else:
					self.log("Didn't match product price: " + product_target_price + " " + response.url + "\n", level=log.WARNING)

			else:
				self.log("Didn't find product price: " + response.url + "\n", level=log.DEBUG)

			# extract product brand
			brand_holder = product_title_holder.select("parent::node()//a[contains(@class,'productBrand')]/a/text()").extract()
			if brand_holder:
				item['product_brand'] = brand_holder[0]
				self.log("Extracted brand: " + item['product_brand'] + " from results page: " + str(response.url), level=log.DEBUG)

			# add result to items
			items.add(item)


		# extract product info from product pages (send request to parse first URL in list)
		# add as meta all that was received as meta, will pass it on to reduceResults function in the end
		# also send as meta the entire results list (the product pages URLs), will receive callback when they have all been parsed

		# send the request back to reduceResults (with updated 'items') whether there are any more pending requests or not
		# if there are, reduceResults will send the next one back here, if not it will return the final result

		response.meta['items'] = items

		# and field 'parsed' to indicate that the call was received from this method (was not the initial one)
		#TODO: do we still need this?
		response.meta['parsed'] = True
		# only send the response we have as an argument, no need to make a new request
		return self.reduceResults(response)

	# create product items from results using product pages (extracting needed info on products from there)
	# parse results page for target, extract info for all products returned by search (keep them in "meta")
	def parseResults_withProductPages(self, response):
		hxs = HtmlXPathSelector(response)

		if 'items' in response.meta:
			items = response.meta['items']
		else:
			items = set()

		# add product URLs to be parsed to this list
		if 'search_results' not in response.meta:
			product_urls_and_names = set()
		else:
			product_urls_and_names = response.meta['search_results']

		results = hxs.select("//div[@class='productTitle']/a")
		for result in results:
			product_url = result.select("@href").extract()[0]
			product_name = result.select("text()").extract()[0]
			product_urls_and_names.add((product_url, product_name))

		# extract product info from product pages (send request to parse first URL in list)
		# add as meta all that was received as meta, will pass it on to reduceResults function in the end
		# also send as meta the entire results list (the product pages URLs), will receive callback when they have all been parsed

		# send the request further to parse product pages only if we gathered all the product URLs from all the queries 
		# (there are no more pending requests)
		# otherwise send them back to reduceResults and wait for the next query, save all product URLs in search_results
		# this way we avoid duplicates
		if product_urls_and_names and ('pending_requests' not in response.meta or not response.meta['pending_requests']):
			# get first url in the list and pop it
			product_url_and_name = product_urls_and_names.pop()
			request = Request(product_url_and_name[0], callback = self.parse_product_target, meta = response.meta)
			request.meta['items'] = items

			# send as meta product name as extracted from results page (to be used if name not found in product page)
			request.meta['product_name'] = product_url_and_name[1]

			# this will be the new product_urls list with the first item popped
			request.meta['search_results'] = product_urls_and_names

			return request

		# if there were no results, the request will never get back to reduceResults
		# so send it from here so it can parse the next queries
		# add to the response the URLs of the products to crawl we have so far, items (handles case when it was not created yet)
		# and field 'parsed' to indicate that the call was received from this method (was not the initial one)
		else:
			response.meta['items'] = items
			response.meta['parsed'] = True
			response.meta['search_results'] = product_urls_and_names
			# only send the response we have as an argument, no need to make a new request
			return self.reduceResults(response)

	# extract product info from a product page for target
	# keep product pages left to parse in 'search_results' meta key, send back to parseResults_new when done with all
	def parse_product_target(self, response):

		hxs = HtmlXPathSelector(response)

		items = response.meta['items']

		#site = response.meta['origin_site']
		origin_url = response.meta['origin_url']

		item = SearchItem()
		item['product_url'] = response.url
		#item['origin_site'] = site
		item['origin_url'] = origin_url
		item['origin_name'] = response.meta['origin_name']

		if 'origin_model' in response.meta:
			item['origin_model'] = response.meta['origin_model']

		# extract product name

		#TODO: is this general enough?
		product_name = hxs.select("//h2[@class='product-name item']/span[@itemprop='name']/text()").extract()

		# if you can't find product name in product page, use the one extracted from results page
		if not product_name:
			item['product_name'] = response.meta['product_name']
			self.log("Error: product name not found on product page, extracted from results page: " + item['product_name'] + " " + origin_url, level=log.INFO)
		else:
			item['product_name'] = product_name[0].strip()

		if not item['product_name']:
			self.log("Error: No product name: " + str(response.url) + " from product: " + origin_url, level=log.INFO)

		else:
			#TODO: no model number field?
			model_number_holder = None
			if model_number_holder:
				item['product_model'] = model_number_holder[0].strip()
			# if no product model explicitly on the page, try to extract it from name
			else:
				product_model_extracted = ProcessText.extract_model_from_name(item['product_name'])
				if product_model_extracted:
					item['product_model'] = product_model_extracted
				#print "MODEL EXTRACTED: ", product_model_extracted, " FROM NAME ", item['product_name'].encode("utf-8")


			#TODO: no brand field?

			# extract price
			#! extracting list price and not discount price when discounts available?
			#TODO: complete this with other types of pages
			price_holder = hxs.select("//span[@class='offerPrice']/text()").extract()

			if price_holder:
				product_target_price = price_holder[0].strip()
				# remove commas separating orders of magnitude (ex 2,000)
				product_target_price = re.sub(",","",product_target_price)
				m = re.match("\$([0-9]+\.?[0-9]*)", product_target_price)
				if m:
					item['product_target_price'] = float(m.group(1))
				else:
					sys.stderr.write("Didn't match product price: " + product_target_price + " " + response.url + "\n")

			else:
				sys.stderr.write("Didn't find product price: " + response.url + "\n")


			# add result to items
			items.add(item)

		# if there are any more results to be parsed, send a request back to this method with the next product to be parsed
		product_urls_and_names = response.meta['search_results']

		if product_urls_and_names:
			product_url_and_name = product_urls_and_names.pop()
			request = Request(product_url_and_name[0], callback = self.parse_product_target, meta = response.meta)
			request.meta['items'] = items
			# eliminate next product from pending list (this will be the new list with the first item popped)

			# send product name with request as well
			request.meta['product_name'] = product_url_and_name[1]
			request.meta['search_results'] = product_urls_and_names

			return request
		else:
			# otherwise, we are done, send a the response back to reduceResults (no need to make a new request)
			# add as meta newly added items
			# also add 'parsed' field to indicate that the parsing of all products was completed and they cand be further used
			# (actually that the call was made from this method and was not the initial one, so it has to move on to the next request)

			response.meta['parsed'] = True
			response.meta['items'] = items

			return self.reduceResults(response)