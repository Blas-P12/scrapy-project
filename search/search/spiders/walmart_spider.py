from scrapy.spider import BaseSpider
from scrapy.selector import HtmlXPathSelector
from scrapy.http import Request
from scrapy.http import TextResponse
from scrapy.http import Response
from scrapy.exceptions import CloseSpider
from search.items import SearchItem
from search.items import WalmartItem
from search.spiders.search_spider import SearchSpider
from scrapy import log

from spiders_utils import Utils
from search.matching_utils import ProcessText

import re
import sys

# spider derived from search spider to search for products on Walmart
class WalmartSpider(SearchSpider):

	name = "walmart"

	# initialize fields specific to this derived spider
	def init_sub(self):
		self.target_site = "walmart"
		self.start_urls = [ "http://www.walmart.com" ]

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



		results = hxs.select("//div[@class='prodInfo']/div[@class='prodInfoBox']/a[@class='prodLink ListItemLink']")
		for result in results:
			item = SearchItem()
			#item['origin_site'] = site

			#TODO: usually the manufacturer is in bold, so maybe use that
			product_name = " ".join(result.select(".//text()").extract())
			# append text that is in <span> if any
			span_text = result.select("./span/text()")

			#TODO: use span text differently, as it is more important/relevant (bold) ?
			for text in span_text:
				product_name += " " + text.extract()
			item['product_name'] = product_name
			rel_url = result.select("@href").extract()[0]
			
			root_url = "http://www.walmart.com"
			item['product_url'] = Utils.add_domain(rel_url, root_url)

			if 'origin_url' in response.meta:
				item['origin_url'] = response.meta['origin_url']

			if 'origin_id' in response.meta:
				request.meta['origin_id'] = response.meta['origin_id']
				assert self.by_id
			else:
				assert not self.by_id


			items.add(item)

		response.meta['items'] = items
		response.meta['parsed'] = items
		return self.reduceResults(response)


# spider that receives a list of Walmart product ids (or of Walmart URLs of the type http://www.walmart.com/<id>)
# and outputs the product's page full URL as found on Walmart
########################
# Run with:
#  scrapy crawl walmart_fullurls -a ids_file=<input_filename> [-a outfile=<output_filename>]
#
#
########################
class WalmartFullURLsSpider(BaseSpider):
	name = "walmart_fullurls"

	allowed_domains = ["walmart.com"]
	start_urls = ["http://www.walmart.com"]

	def __init__(self, ids_file, outfile=None):
		self.ids_file = ids_file
		self.outfile = outfile

		# extract ids from URLs in input file (of type http://www.walmart.com/ip/<id>) and store them in a list
		self.walmart_ids = []
		with open(self.ids_file, "r") as infile:
			for line in infile:
				m = re.match("http://www.walmart.com/ip/([0-9]+)", line.strip())
				if m:
					walmart_id = m.group(1)
					self.walmart_ids.append(walmart_id)
				else:
					self.log("ERROR: Invalid (short) URL file" + "\n", level = log.ERROR)
					#raise CloseSpider("Invalid (short) URL file")

		# this option is needed in middlewares.py used by all spiders
		self.use_proxy = False

	# build URL for search page with a specific search query. to be used with product ids as queries
	def build_search_page(self, query):
		searchpage_URL = "http://www.walmart.com/search/search-ng.do?ic=16_0&Find=Find&search_query=%s&Find=Find&search_constraint=0" % query
		return searchpage_URL

	# check if URL contains the product's id (therefore is valid)
	def valid_result(self, url, prod_id):
		return "/"+prod_id in url

	def parse(self, response):
		# take every id and pass it to the method that retrieves its URL, build an item for each of it
		for walmart_id in self.walmart_ids:
			item = WalmartItem()
			item['walmart_id'] = walmart_id
			item['walmart_short_url'] = "http://www.walmart.com/ip/" + walmart_id

			# search for this id on Walmart, get the results page
			search_page = self.build_search_page(walmart_id)
			request = Request(search_page, callback = self.parse_resultsPage, meta = {"item": item})
			yield request

	# get URL of first result from search page (search by product id)
	def parse_resultsPage(self, response):
		hxs = HtmlXPathSelector(response)
		item = response.meta['item']
		result = hxs.select("//div[@class='prodInfo']/div[@class='prodInfoBox']/a[@class='prodLink ListItemLink'][position()<2]/@href").extract()
		if result:
			item['walmart_full_url'] = Utils.add_domain(result[0], "http://www.walmart.com")

			# id should be somewhere in the full URL as well
			if self.valid_result(item['walmart_full_url'], item['walmart_id']):
				return item
			else:
				# search again, but select result that contains id
				#OBS: non optimal, should do selecting here
				return Request(response.url, callback = self.parse_resultsPage2, meta = {"item":item})
		else:
			# try to find result by using the product name instead

			# get product name from product page, then search by it
			return Request(item['walmart_short_url'], callback = self.getProductName, meta = {"item":item})
			#self.log("No results for short_url " + item['walmart_short_url'] + "\n", level=log.ERROR)

	def getProductName(self, response):
		hxs = HtmlXPathSelector(response)
		title_holder = hxs.select("//h1[@class='productTitle']/text()").extract()
		if title_holder:
			product_name = title_holder[0]

			# search by product name
			search_query = "+".join(product_name.split())
			search_page = self.build_search_page(search_query)
			return Request(search_page, callback = self.parse_resultsPage2, meta = {"item" : response.meta['item']})

		else:
			self.log("No results for short_url (didn't find product name) " + response.url + "\n", level=log.ERROR)

	# parse results page from search by product name - find URL that contains item id, if any
	def parse_resultsPage2(self, response):
		hxs = HtmlXPathSelector(response)

		item = response.meta['item']
		results = hxs.select("//div[@class='prodInfo']/div[@class='prodInfoBox']/a[@class='prodLink ListItemLink']/@href").extract()
		for result in results:
			# if the result URL contains the id, this is the correct result
			if self.valid_result(item['walmart_id'], result):
				product_url = Utils.add_domain(result, "http://www.walmart.com")
				item['walmart_full_url'] = product_url
				return item


		# no results matching the condition were found
		self.log("No results for short_url (didn't find any URLs containing id) " + item['walmart_short_url'] + "\n", level=log.ERROR)






