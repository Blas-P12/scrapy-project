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

class EbaySpider(SearchSpider):

	name = "ebay"

	# initialize fields specific to this derived spider
	def init_sub(self):
		self.target_site = "ebay"
		self.start_urls = [ "http://www.ebay.com" ]

	def parseResults(self, response):

		hxs = HtmlXPathSelector(response)

		#site = response.meta['origin_site']
		origin_name = response.meta['origin_name']
		origin_model = response.meta['origin_model']

		# if this comes from a previous request, get last request's items and add to them the results

		if 'items' in response.meta:
			items = response.meta['items']
		else:
			items = set()

		# add product URLs to be parsed to this list
		if 'search_results' not in response.meta:
			product_urls = set()
		else:
			product_urls = response.meta['search_results']



		results = hxs.select("//div[@id='ResultSetItems']//h4/a | //div[@id='PaginationAndExpansionsContainer']//h4/a")
		for result in results:
			product_url = result.select("@href").extract()[0]

			product_urls.add(product_url)

		# extract product info from product pages (send request to parse first URL in list)
		# add as meta all that was received as meta, will pass it on to reduceResults function in the end
		# also send as meta the entire results list (the product pages URLs), will receive callback when they have all been parsed

		# send the request further to parse product pages only if we gathered all the product URLs from all the queries 
		# (there are no more pending requests)
		# otherwise send them back to parseResults and wait for the next query, save all product URLs in search_results
		# this way we avoid duplicates
		if product_urls and ('pending_requests' not in response.meta or not response.meta['pending_requests']):
			request = Request(product_urls.pop(), callback = self.parse_product_ebay, meta = response.meta)
			request.meta['items'] = items

			# this will be the new product_urls list with the first item popped
			request.meta['search_results'] = product_urls

			return request

		# if there were no results, the request will never get back to reduceResults
		# so send it from here so it can parse the next queries
		# add to the response the URLs of the products to crawl we have so far, items (handles case when it was not created yet)
		# and field 'parsed' to indicate that the call was received from this method (was not the initial one)
		else:
			response.meta['items'] = items
			response.meta['parsed'] = True
			response.meta['search_results'] = product_urls
			# only send the response we have as an argument, no need to make a new request
			return self.reduceResults(response)



	def parse_product_ebay(self, response):
		hxs = HtmlXPathSelector(response)

		items = response.meta['items']

		#site = response.meta['origin_site']
		origin_url = response.meta['origin_url']

		item = SearchItem()
		item['product_url'] = response.url
		#item['origin_site'] = site
		item['origin_url'] = origin_url

		if 'origin_id' in response.meta:
			item['origin_id'] = response.meta['origin_id']
			assert self.by_id
		else:
			assert not self.by_id

		# extract product name
		product_name = hxs.select("//h1[@id='itemTitle']/text()").extract()
		if not product_name:
			self.log("Error: No product name: " + str(response.url), level=log.INFO)

		else:

			item['product_name'] = product_name[0]

			# extract product brand
			product_brand_holder = hxs.select("//td[@class='attrLabels'][contains(normalize-space(),'Brand')]" + \
				"/following-sibling::node()[normalize-space()!=''][1]//text()[normalize-space()!='']").extract()
			if product_brand_holder:
				item['product_brand'] = product_brand_holder[0]

			# extract product model
			product_model_holder = hxs.select("//td[@class='attrLabels'][contains(normalize-space(),'Model')]" + \
				"/following-sibling::node()[normalize-space()!=''][1]//text()[normalize-space()!='']").extract()
			if not product_model_holder:
				product_model_holder = hxs.select("//td[@class='attrLabels'][contains(normalize-space(),'MPN')]" + \
				"/following-sibling::node()[normalize-space()!=''][1]//text()[normalize-space()!='']").extract()

			if product_model_holder:
				item['product_model'] = product_model_holder[0]

			# add result to items
			items.add(item)

		# if there are any more results to be parsed, send a request back to this method with the next product to be parsed
		product_urls = response.meta['search_results']

		if product_urls:
			request = Request(product_urls.pop(), callback = self.parse_product_ebay, meta = response.meta)
			request.meta['items'] = items
			# eliminate next product from pending list (this will be the new list with the first item popped)
			request.meta['search_results'] = product_urls

			return request
		else:
			# otherwise, we are done, send a the response back to reduceResults (no need to make a new request)
			# add as meta newly added items
			# also add 'parsed' field to indicate that the parsing of all products was completed and they cand be further used
			# (actually that the call was made from this method and was not the initial one, so it has to move on to the next request)

			response.meta['parsed'] = True
			response.meta['items'] = items

			return self.reduceResults(response)
