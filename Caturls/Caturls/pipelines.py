# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: http://doc.scrapy.org/topics/item-pipeline.html

class CaturlsPipeline(object):
	def __init__(self):
		self.urls = []

	def open_spider(self, spider):
		self.file = open(spider.outfile, 'wb')
	
	def process_item(self, item, spider):
		line = item['product_url'] + "\n"
		# avoid duplicates
		if item['product_url'] not in self.urls:
			self.urls.append(item['product_url'])
			self.file.write(line)
			return item

	def close_spider(self, spider):
		self.file.close()
