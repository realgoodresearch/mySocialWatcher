from mysocialwatcher.crawler.utils import *
from dotenv import load_dotenv

load_dotenv()  # load_dotenv('./config/private/crawler.env')
token = os.environ.get('API_TOKEN')  # 
url = os.environ.get('API_URL')  # url = 'http://127.0.0.1/api/v1/write' / ASW API url = 'http://18.135.72.18/api/v1/social_media_audience/write'
data_dir = os.environ.get('DATA_DIR')  # data_dir = 'C:/Users/edithd/Documents/mySocialWatcher/data/saffron'
api_mode = os.environ.get('API_MODE', 'v1').lower()
api_batch_size = int(os.environ.get('API_BATCH_SIZE', '500'))
registry_mode = os.environ.get('REGISTRY_MODE', 'off').lower()
registry_url = os.environ.get('REGISTRY_URL')
registry_instance = os.environ.get('CRAWLER_INSTANCE', 'crawler')
registry_lease_seconds = int(os.environ.get('REGISTRY_LEASE_SECONDS', '900'))
crawl_date_from = os.environ.get('CRAWL_DATE_FROM')
crawl_date_to = os.environ.get('CRAWL_DATE_TO')
crawl_path_prefix = os.environ.get('CRAWL_PATH_PREFIX')


if __name__ == "__main__":

    crawler(data_dir=data_dir,
            token=token,
            url=url,
            api_mode=api_mode,
            batch_size=api_batch_size,
            registry_mode=registry_mode,
            registry_url=registry_url,
            crawler_instance=registry_instance,
            registry_lease_seconds=registry_lease_seconds,
            crawl_date_from=crawl_date_from,
            crawl_date_to=crawl_date_to,
            crawl_path_prefix=crawl_path_prefix)
