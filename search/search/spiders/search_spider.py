from scrapy.spider import BaseSpider
from scrapy.selector import HtmlXPathSelector
from scrapy.http import Request
from scrapy.http import TextResponse
from scrapy.http import Response
from scrapy.exceptions import CloseSpider
from search.items import SearchItem
from scrapy import log

from spiders_utils import Utils
from search.matching_utils import ProcessText

import re
import sys
import json

# from selenium import webdriver
# import time

################################
# Run with 
#
#   scrapy crawl <site> -a product_name="<name>" [-a output="<option(1/2)>"] [-a threshold=<value>] [a outfile="<filename>"] [-a fast=0]
#      -- or --
#   scrapy crawl <site> -a product_url="<url>" [-a output="<option(1/2)>"] [-a threshold=<value>] [a outfile="<filename>""] [-a fast=0]
#      -- or --
#   scrapy crawl <site> -a product_urls_file="<filename>" [-a output="<option(1/2)>"] [-a threshold=value] [a outfile="<filename>"] [-a fast=0]
#      -- or --
#   scrapy crawl <site> -a walmart_ids_file="<filename>" [-a output="<option(1/2)>"] [-a threshold=value] [a outfile="<filename>"] [-a fast=0]
# 
# where <site> is the derived spider corresponding to the site to search on 
#
# Usage example:
#
# scrapy crawl amazon -a product_urls_file="../sample_output/walmart_televisions_urls.txt" -a output=2 -a outfile="search_results_1.4.txt" -a threshold=1.4 -s LOG_ENABLED=1 2>search_log_1.4.out
#
################################


# search for a product in all sites, using their search functions; give product as argument by its name or its page url
class SearchSpider(BaseSpider):

	name = "search"
	# amazon_cookie_header = "x-wl-uid=1Y9x3Q0Db5VX3Xvh1wKV9kdGsDEeLDkceSgPK5Hq+AhrYZKCWSHWq6CeCiAwA7BsYZQ58tkG8c3c=; session-token=JPU0C93JOc0DMIZwsQTlpZFJAADURltK2s5Cm22nmFGmaGRwiOPKdvd+ALLsrWay07GVVQtBquy/KpNSTFb5e0HfWeHAq92jFhXz5nQouwyqMLtEC3MUu2TWkIRGps4ppDXQfMP/r96gq0QfRR8EdPogbQ9RzEXoIKf3tj3klxeO2mT6xVQBTfpMPbQHQtv8uyFjWgkLtp6upe4eWorbpd/KyWlBSQXD4eiyfQLIC480TxbOvCBmDhGBOqf6Hk0Nprh2OO2EfrI=; x-amz-captcha-1=1391100438353490; x-amz-captcha-2=+EDhq9rcotSRn783vYMxdQ==; csm-hit=337.71|1391093239619; ubid-main=188-7820618-3817319; session-id-time=2082787201l; session-id=177-0028713-4113141"
	# amazon_cookies = {"x-wl-uid" : "1Y9x3Q0Db5VX3Xvh1wKV9kdGsDEeLDkceSgPK5Hq+AhrYZKCWSHWq6CeCiAwA7BsYZQ58tkG8c3c=", \
	# "session-token" : "JPU0C93JOc0DMIZwsQTlpZFJAADURltK2s5Cm22nmFGmaGRwiOPKdvd+ALLsrWay07GVVQtBquy/KpNSTFb5e0HfWeHAq92jFhXz5nQouwyqMLtEC3MUu2TWkIRGps4ppDXQfMP/r96gq0QfRR8EdPogbQ9RzEXoIKf3tj3klxeO2mT6xVQBTfpMPbQHQtv8uyFjWgkLtp6upe4eWorbpd/KyWlBSQXD4eiyfQLIC480TxbOvCBmDhGBOqf6Hk0Nprh2OO2EfrI=",\
	# "x-amz-captcha-1" : "1391100438353490" , "x-amz-captcha-2" : "+EDhq9rcotSRn783vYMxdQ==", "csm-hit" : "337.71|1391093239619", "ubid-main" : "188-7820618-3817319",\
	# "session-id-time" : "2082787201l", "session-id" : "177-0028713-4113141"}

	allowed_domains = ["amazon.com", "walmart.com", "bloomingdales.com", "overstock.com", "wayfair.com", "bestbuy.com", "toysrus.com",\
					   "bjs.com", "sears.com", "staples.com", "newegg.com", "ebay.com", "target.com", "sony.com", "samsung.com"]

	# pass product as argument to constructor - either product name or product URL
	# arguments:
	#				product_name - the product's name, for searching by product name
	#				product_url - the product's page url in the source site, for searching by product URL
	#				product_urls_file - file containing a list of product pages URLs
	#				output - integer(1/2) option indicating output type (either result URL (1), or result URL and source product URL (2))
	#				threshold - parameter for selecting results (the lower the value the more permissive the selection)
	def __init__(self, product_name = None, product_url = None, product_urls_file = None, walmart_ids_file = None, \
		output = 2, threshold = 1.0, outfile = "search_results.csv", outfile2 = "not_matched.csv", fast = 0, use_proxy = False, manufacturer_site = None, cookies_file = None):#, by_id = False):

		# call specific init for each derived class
		self.init_sub()

		self.product_url = product_url
		self.product_name = product_name
		self.output = int(output)
		self.product_urls_file = product_urls_file
		self.walmart_ids_file = walmart_ids_file
		self.threshold = float(threshold)
		self.outfile = outfile
		self.outfile2 = outfile2
		self.fast = fast
		self.use_proxy = use_proxy
		self.manufacturer_site = manufacturer_site
		#self.by_id = by_id

		# set cookies
		self.cookies_file = cookies_file
		if cookies_file:
			self.cookies = json.load(open(cookies_file, "r"))
			self.amazon_cookies = self.cookies['amazon_cookies']
			amazon_cookie_header = ""
			for cookie in self.amazon_cookies:
				amazon_cookie_header += cookie + "=" + self.amazon_cookies[cookie] + "; "
			self.amazon_cookie_header = amazon_cookie_header


	def build_search_pages(self, search_query):
		# build list of urls = search pages for each site
		search_pages = {
						"amazon" : "http://www.amazon.com/s/ref=nb_sb_noss?url=search-alias%3Daps&field-keywords=" + search_query, \
						"walmart" : "http://www.walmart.com/search/search-ng.do?ic=16_0&Find=Find&search_query=%s&Find=Find&search_constraint=0" % search_query, \
						"bloomingdales" : "http://www1.bloomingdales.com/shop/search?keyword=%s" % search_query, \
						"overstock" : "http://www.overstock.com/search?keywords=%s" % search_query, \
						"wayfair" : "http://www.wayfair.com/keyword.php?keyword=%s" % search_query, \
						# #TODO: check this URL
						"bestbuy" : "http://www.bestbuy.com/site/searchpage.jsp?_dyncharset=ISO-8859-1&_dynSessConf=-26268873911681169&id=pcat17071&type=page&st=%s&sc=Global&cp=1&nrp=15&sp=&qp=&list=n&iht=y&fs=saas&usc=All+Categories&ks=960&saas=saas" % search_query, \
						"toysrus": "http://www.toysrus.com/search/index.jsp?kw=%s" % search_query, \
						# #TODO: check the keywords, they give it as caps
						# "bjs" : "http://www.bjs.com/webapp/wcs/stores/servlet/Search?catalogId=10201&storeId=10201&langId=-1&pageSize=40&currentPage=1&searchKeywords=%s&tASearch=&originalSearchKeywords=lg+life+is+good&x=-1041&y=-75" % search_query, \
						# #TODO: check this url
						# "sears" : "http://www.sears.com/search=%s" % search_query}
						# #TODO: staples?
						"ebay": "http://www.ebay.com/sch/i.html?_trksid=p2050601.m570.l1313&_nkw=%s" % search_query, \
						"sony": "http://store.sony.com/search?SearchTerm=%s" % search_query, \
						"samsung": "http://www.samsung.com/us/function/search/espsearchResult.do?input_keyword=%s" % search_query, \
						"target" : "http://www.target.com/s?searchTerm=" + search_query + "&category=0%7CAll%7Cmatchallpartial%7Call+categories&lnk=snav_sbox_" + search_query

						}

		return search_pages

	def build_search_query(self, product_name):
		# put + instead of spaces, lowercase all words
		search_query = "+".join(ProcessText.normalize(product_name, stem=False, exclude_stopwords=False))
		return search_query


	# parse input and build list of URLs to find matches for, send them to parseURL
	def parse(self, response):

		if self.product_name:

			# can inly use this option if self.target_site has been initialized (usually true for spiders for retailers sites, not true for manufacturer's sites)
			if not self.target_site:
				self.log("You can't use the product_name option without setting the target site to search on\n", level=log.ERROR)
				raise CloseSpider("\nYou can't use the product_name option without setting the target site to search on\n")

			search_query = self.build_search_query(self.product_name)
			search_pages = self.build_search_pages(search_query)

			request = Request(search_pages[self.target_site], callback = self.parseResults)

			# set amazon cookies
			if (self.target_site == 'amazon' and self.cookies_file):
				request.cookies = self.amazon_cookies
				request.headers['Cookies'] = self.amazon_cookie_header
				#request.meta['dont_merge_cookies'] = True
				## print "SET AMAZON COOKIES"

			request.meta['origin_name'] = self.product_name
			request.meta['query'] = search_query

			# just use empty product model and url, for compatibility, also pending_requests
			request.meta['origin_model']  = ''
			request.meta['origin_url'] = ''
			request.meta['pending_requests'] = []

			yield request
		
		# if we have product URLs, pass them to parseURL to extract product names (which will pass them to parseResults)
		product_urls = []
		# if we have a single product URL, create a list of URLs containing it
		if self.product_url:
			product_urls.append(self.product_url)

		# if we have a file with a list of URLs, create a list with URLs found there
		if self.product_urls_file:
			f = open(self.product_urls_file, "r")
			for line in f:
				product_urls.append(line.strip())
			f.close()

		for product_url in product_urls:
			# extract site domain
			
			# m = re.match("http://www1?\.([^\.]+)\.com.*", product_url)
			# origin_site = ""
			# if m:
			# 	origin_site = m.group(1)
			# else:
			# 	sys.stderr.write('Can\'t extract domain from URL.\n')
			origin_site = Utils.extract_domain(product_url)
			
			request = Request(product_url, callback = self.parseURL)
			request.meta['origin_site'] = origin_site
			if origin_site == 'staples':
				zipcode = "12345"
				request.cookies = {"zipcode": zipcode}
				request.meta['dont_redirect'] = True
			yield request

		# if we have a file with Walmart ids, create a list of the ids there
		if self.walmart_ids_file:
			walmart_ids = []
			f = open(self.walmart_ids_file, "r")
			for line in f:
				if "," in line:
					id_string = line.strip().split(",")[0]
				else:
					id_string = line.strip()
				if re.match("[0-9]+", id_string):
					walmart_ids.append(id_string)
			f.close()		

			self.by_id = True

			for walmart_id in walmart_ids:
				# create Walmart URLs based on these IDs
				walmart_url = Utils.add_domain(walmart_id, "http://www.walmart.com/ip/")
				request = Request(walmart_url, callback = self.parseURL)
				#request.meta['origin_site'] = 'walmart'
				yield request
		

	# parse a product page (given its URL) and extract product's name;
	# create queries to search by (use model name, model number, and combinations of words from model name), then send them to parseResults
	#TODO: refactor
	def parseURL(self, response):

		site = response.meta['origin_site']
		hxs = HtmlXPathSelector(response)

		product_model = ""

		product_brand = ""
		product_price = ""


		#############################################################3
		# Extract product attributes (differently depending on site)

		if site == 'staples':

			product_name = hxs.select("//h1/text()").extract()[0]

			model_nodes = hxs.select("//p[@class='itemModel']/text()").extract()
			if model_nodes:
				model_node = model_nodes[0]

				model_node = re.sub("\W", " ", model_node, re.UNICODE)
				m = re.match("(.*)Model:(.*)", model_node.encode("utf-8"), re.UNICODE)
				
				
				if m:
					product_model = m.group(2).strip()

		elif site == 'walmart':
			product_name_holder = hxs.select("//h1[@class='productTitle']/text()").extract()
			if product_name_holder:
				product_name = product_name_holder[0].strip()

				# get integer part of product price
				product_price_big = hxs.select("//span[@class='bigPriceText1']/text()").extract()

				if not product_price_big:
					self.log("Didn't find product price: " + response.url + "\n", level=log.DEBUG)
				# if there is a range of prices take their average
				if len(product_price_big) > 1:

					# remove $ and .
					product_price_min = re.sub("[\$\.,]", "", product_price_big[0])
					product_price_max = re.sub("[\$\.,]", "", product_price_big[-1])

					#TODO: check if they're ints?
					product_price_big = (int(product_price_min) + int(product_price_max))/2.0

				elif product_price_big:
					product_price_big = int(re.sub("[\$\.,]", "", product_price_big[0]))

				# get fractional part of price
				#TODO - not that important

				if product_price_big:
					product_price = product_price_big



			else:
				sys.stderr.write("Broken product page link (can't find item title): " + response.url + "\n")
				# return the item as a non-matched item
				item = SearchItem()
				#item['origin_site'] = site
				item['origin_url'] = response.url
				# remove unnecessary parameters
				m = re.match("(.*)\?enlargedSearch.*", item['origin_url'])
				if m:
					item['origin_url'] = m.group(1)
				#item['origin_id'] = self.extract_walmart_id(item['origin_url'])
				if self.name != 'manufacturer':
					# don't return empty matches in manufacturer spider
					yield item
				return

			#TODO: if it contains 2 words, first could be brand - also add it in similar_names function
			product_model_holder = hxs.select("//td[contains(text(),'Model')]/following-sibling::*/text()").extract()
			if product_model_holder:
				product_model = product_model_holder[0]

		#TODO: for the sites below, complete with missing logic, for not returning empty elements in manufacturer spider
		elif site == 'newegg':
			product_name_holder = hxs.select("//span[@itemprop='name']/text()").extract()
			if product_name_holder:
				product_name = product_name_holder[0].strip()
			else:
				sys.stderr.write("Broken product page link (can't find item title): " + response.url + "\n")
				item = SearchItem()
				#item['origin_site'] = site
				item['origin_url'] = response.url
				yield item
				return
			product_model_holder = hxs.select("//dt[text()='Model']/following-sibling::*/text()").extract()
			if product_model_holder:
				product_model = product_model_holder[0]


		else:
			raise CloseSpider("Unsupported site: " + site)

		if site == 'staples':
			zipcode = "12345"
			cookies = {"zipcode": zipcode}
		else:
			cookies = {}


		#######################################################################
		# Create search queries to the second site, based on product attributes

		request = None

		#TODO: search by alternative model numbers?

		#TODO: search by model number extracted from product name? Don't I do that implicitly? no, but in combinations

		# if there is no product model, try to extract it
		if not product_model:
			product_model = ProcessText.extract_model_from_name(product_name)

			# for logging purposes, set this back to the empty string if it wasn't found (so was None)
			if not product_model:
				product_model = ""

			# product_model_index = ProcessText.extract_model_nr_index(product_name)
			# if product_model_index >= 0:
			# 	product_model = product_name[product_model_index]
				
			## print "MODEL EXTRACTED: ", product_model, " FROM NAME ", product_name

		# if there is no product brand, get first word in name, assume it's the brand
		product_brand_extracted = ""
		#product_name_tokenized = ProcessText.normalize(product_name)
		product_name_tokenized = [word.lower() for word in product_name.split(" ")]
		#TODO: maybe extract brand as word after 'by', if 'by' is somewhere in the product name
		if len(product_name_tokenized) > 0 and re.match("[a-z]*", product_name_tokenized[0]):
			product_brand_extracted = product_name_tokenized[0].lower()

		# if we are in manufacturer spider, set target_site to manufacturer site

		# for manufacturer spider set target_site of request to brand extracted from name for this particular product
		if self.name == 'manufacturer':

			#TODO: restore commented code; if brand not found, try to search for it on every manufacturer site (build queries fo every supported site)
			# hardcode target site to sony
			#self.target_site = 'sony'
			#self.target_site = product_brand_extracted

			#target_site = product_brand_extracted

			# can only go on if site is supported
			# (use dummy query)
			#if target_site not in self.build_search_pages("").keys():
			if product_brand_extracted not in self.build_search_pages("").keys():

				product_brands_extracted = set(self.build_search_pages("").keys()).intersection(set(product_name_tokenized))
				
				if product_brands_extracted:
					product_brand_extracted = product_brands_extracted.pop()
					#target_site = product_brand_extracted
				else:
					# give up and return item without match
					self.log("Manufacturer site not supported (" + product_brand_extracted + ") or not able to extract brand from product name (" + product_name + ")\n", level=log.ERROR)

					## comment lines below to: don't return anything if you can't search on manufacturer site
					# item = SearchItem()
					# item['origin_url'] = response.url
					# item['origin_name'] = product_name
					# if product_model:
					# 	item['origin_model'] = product_model
					# yield item
					return

			# if specific site is not set, search on manufacturer site as extracted from name
			if not self.manufacturer_site:
				target_site = product_brand_extracted
			else:
				# if it's set, continue only if it matches extracted brand
				if self.manufacturer_site!= product_brand_extracted:
					self.log("Will abort matching for product, extracted brand does not match specified manufacturer option (" + product_brand_extracted + ")\n", level=log.INFO)

					## comment lines below to: don't return anything if you can't search on manufacturer site
					# item = SearchItem()
					# item['origin_url'] = response.url
					# item['origin_name'] = product_name
					# if product_model:
					# 	item['origin_model'] = product_model
					# yield item
					return

				else:
					target_site = product_brand_extracted


					# # try to match it without specific site (manufacturer spider will try to search on all manufacturer sites)
					# target_site = None



		# for other (site specific) spiders, set target_site of request to class variable self.target_site set in class "constructor" (init_sub)
		else:
			target_site = self.target_site


		# 1) Search by model number
		if product_model:

			#TODO: model was extracted with ProcessText.extract_model_from_name(), without lowercasing, should I lowercase before adding it to query?
			query1 = self.build_search_query(product_model)
			search_pages1 = self.build_search_pages(query1)
			#page1 = search_pages1[self.target_site]
			page1 = search_pages1[target_site]

			request1 = Request(page1, callback = self.parseResults)

			# set amazon cookies
			if (self.target_site == 'amazon' and self.cookies_file):
				request1.cookies = self.amazon_cookies
				request1.headers['Cookies'] = self.amazon_cookie_header
				#request1.meta['dont_merge_cookies'] = True
				## print "SET AMAZON COOKIES"

			request1.meta['query'] = query1
			request1.meta['target_site'] = target_site
			
			request = request1


		# 2) Search by product full name
		query2 = self.build_search_query(product_name)
		search_pages2 = self.build_search_pages(query2)
		#page2 = search_pages2[self.target_site]
		page2 = search_pages2[target_site]
		request2 = Request(page2, callback = self.parseResults)

		# set cookies for amazon
		if (self.target_site == 'amazon' and self.cookies_file):
				request2.cookies = self.amazon_cookies
				request2.headers['Cookies'] = self.amazon_cookie_header
				#request2.meta['dont_merge_cookies'] = True

		request2.meta['query'] = query2
		request2.meta['target_site'] = target_site

		pending_requests = []

		if not request:
			request = request2
		else:
			pending_requests.append(request2)

		# 3) Search by combinations of words in product's name
		# create queries

		for words in ProcessText.words_combinations(product_name, fast=self.fast):
			query3 = self.build_search_query(" ".join(words))
			search_pages3 = self.build_search_pages(query3)
			#page3 = search_pages3[self.target_site]
			page3 = search_pages3[target_site]
			request3 = Request(page3, callback = self.parseResults)

			# set amazon cookies
			if (self.target_site == 'amazon' and self.cookies_file):
				request3.cookies = self.amazon_cookies
				request3.headers['Cookies'] = self.amazon_cookie_header
				#request3.meta['dont_merge_cookies'] = True

			request3.meta['query'] = query3
			request3.meta['target_site'] = target_site


			pending_requests.append(request3)

		request.meta['pending_requests'] = pending_requests
		#request.meta['origin_site'] = 
		# product page from source site
		#TODO: clean this URL? for walmart it added something with ?enlargedsearch=True
		request.meta['origin_url'] = response.url

		request.meta['origin_name'] = product_name
		request.meta['origin_model'] = product_model
		if product_price:
			request.meta['origin_price'] = product_price

		# origin product brand as extracted from name (basically the first word in the name)
		request.meta['origin_brand_extracted'] = product_brand_extracted

		# if self.by_id:
		# 	request.meta['origin_id'] = self.extract_walmart_id(response.url)

		#self.target_site = product_brand_extracted
		#TODO: should this be here??
		target_site = product_brand_extracted

		# print "SENDING REQUEST FOR ", product_name, response.url

		yield request


	# parse results page, handle each site separately

	# recieve requests for search pages with queries as:
	# 1) product model (if available)
	# 2) product name
	# 3) parts of product's name

	# accumulate results for each (sending the pending requests and the partial results as metadata),
	# and lastly select the best result by selecting the best match between the original product's name and the result products' names
	def reduceResults(self, response):

		# print "IN REDUCE RESULTS"

		items = response.meta['items']
		#site = response.meta['origin_site']

		#TODO: do we still need this?
		if 'parsed' not in response.meta:

			# pass to specific prase results function (in derived class)
			return self.parseResults(response)

		else:
			del response.meta['parsed']


		## print stuff
		self.log("PRODUCT: " + response.meta['origin_name'].encode("utf-8") + " MODEL: " + response.meta['origin_model'].encode("utf-8"), level=log.DEBUG)
		self.log( "QUERY: " + response.meta['query'], level=log.DEBUG)
		self.log( "MATCHES: ", level=log.DEBUG)
		for item in items:
			self.log( item['product_name'].encode("utf-8"), level=log.DEBUG)
		self.log( '\n', level=log.DEBUG)


		# if there is a pending request (current request used product model, and pending request is to use product name),
		# continue with that one and send current results to it as metadata
		if 'pending_requests' in response.meta:
			# yield first request in queue and send the other ones as metadata
			pending_requests = response.meta['pending_requests']

			if pending_requests:
				# print "PENDING REQUESTS FOR", response.meta['origin_url'], response.meta['origin_name']
				request = pending_requests[0]

				# update pending requests
				request.meta['pending_requests'] = pending_requests[1:]

				request.meta['items'] = items

				#request.meta['origin_site'] = response.meta['origin_site']
				# product page from source site
				request.meta['origin_url'] = response.meta['origin_url']
				request.meta['origin_name'] = response.meta['origin_name']
				request.meta['origin_model'] = response.meta['origin_model']
				if 'origin_price' in response.meta:
					request.meta['origin_price'] = response.meta['origin_price']
				request.meta['origin_brand_extracted'] = response.meta['origin_brand_extracted']
				if 'threshold' in response.meta:
					request.meta['threshold'] = response.meta['threshold']

				# if 'origin_id' in response.meta:
				# 	request.meta['origin_id'] = response.meta['origin_id']
				# 	assert self.by_id
				# else:
				# 	assert not self.by_id

				# used for result product URLs
				if 'search_results' in response.meta:
					request.meta['search_results'] = response.meta['search_results']

				return request

			# if there are no more pending requests, use cumulated items to find best match and send it as a result
			else:

				# print "DONE FOR ", response.meta['origin_url'], response.meta['origin_name']

				best_match = None

				if items:

					# from all results, select the product whose name is most similar with the original product's name
					# if there was a specific threshold set in request, use that, otherwise, use the class variable
					if 'threshold' in response.meta:
						threshold = response.meta['threshold']
					else:
						threshold = self.threshold

					if 'origin_price' in response.meta:
						product_price = response.meta['origin_price']
						## print "PRICE:", product_price
					else:
						product_price = None
						## print "NO PRICE"
					best_match = ProcessText.similar(response.meta['origin_name'], response.meta['origin_model'], product_price, items, threshold)

					# #self.log( "ALL MATCHES: ", level=log.WARNING)					
					# for item in items:
					# 	## print item['product_name'].encode("utf-8")
					# ## print '\n'

				self.log( "FINAL: " + str(best_match), level=log.WARNING)
				self.log( "\n----------------------------------------------\n", level=log.WARNING)

				if not best_match:
					# if there are no results but the option was to include original product URL, create an item with just that
					# output item if match not found for either output type
					#if self.output == 2:
					item = SearchItem()
					#item['origin_site'] = site
					
					item['origin_url'] = response.meta['origin_url']
					item['origin_name'] = response.meta['origin_name']
					if 'origin_model' in response.meta:
						item['origin_model'] = response.meta['origin_model']

					# if 'origin_id' in response.meta:
					# 	item['origin_id'] = response.meta['origin_id']
					# 	assert self.by_id
					# else:
					# 	assert not self.by_id
					return [item]

				return best_match

		else:
			# output item if match not found
			item = SearchItem()
			#item['origin_site'] = site

			# print "DONE FOR ", response.meta['origin_name']
			
			item['origin_url'] = response.meta['origin_url']
			item['origin_name'] = response.meta['origin_name']

			# if 'origin_id' in response.meta:
			# 	item['origin_id'] = response.meta['origin_id']
			# 	assert self.by_id
			# else:
			# 	assert not self.by_id

			#TODO: uncomment below - it should not have been in if/else branch!

			self.log( "FINAL: " + str(item), level=log.WARNING)
			self.log( "\n----------------------------------------------\n", level=log.WARNING)

			return [item]

	def extract_walmart_id(self, url):
		m = re.match(".*/ip/([0-9]+)", url)
		if m:
			return m.group(1)