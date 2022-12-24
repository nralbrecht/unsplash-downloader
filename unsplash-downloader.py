import os
import time
import math
import json
import random
import requests
import pyjson5 as json5
from multiprocessing.pool import ThreadPool


class UnsplashImage(json.JSONEncoder):
    def __init__(self, id, width, height, color, username, url, website):
        self.id = id
        self.width = width
        self.height = height
        self.color = color
        self.username = username
        self.url = url
        self.website = website
        self.filename = "{}_{}_{}x{}.jpg".format(self.id, self.username, self.width, self.height)

    def download(self, basepath):
        full_path = basepath + self.filename

        if os.path.exists(full_path):
            return

        r = requests.get(self.url, stream=True)

        if r.status_code == 200:
            with open(full_path, "wb") as f:
                for chunk in r:
                    f.write(chunk)
        else:
            print(f"unable to request '{self.id}': response code {r.status_code}")

    def is_valid(self):
        if self.width > 1 and self.height > 1:
            return True
        else:
            return False

    def __str__(self):
     return json.dumps(self.__dict__)

class UnsplashDownloader():
    def __init__(self, config):
        self.config = config

        self.ratelimit_limit = None
        self.ratelimit_remaining = None

        self.download_queue = []

    def _unsplash_request(self, endpoint, params):
        response = requests.get("https://api.unsplash.com/" + endpoint,
            params = params,
            headers = {
                "Authorization": "Client-ID " + self.config["unsplash_app_access_key"],
                "Accept-Version": "v1"
            }
        )

        try:
            self.ratelimit_limit = response.headers["X-Ratelimit-Limit"]
            self.ratelimit_remaining = response.headers["X-Ratelimit-Remaining"]

            print("{}/{} requests to the unsplash api left".format(self.ratelimit_remaining, self.ratelimit_limit))
        except:
            pass

        response.raise_for_status()

        return response

    def _unsplash_search_total_pages(self, query):
        r = self._unsplash_request("search/photos", {
            "query": query,
            "page": 1,
            "per_page": 1,
            "order_by": self.config["order_by"],
            "content_filter": self.config["content_filter"],
            "orientation": self.config["orientation"]
        })

        return math.ceil(r.json()["total"] / self.config["max_per_page"])

    def _get_unsplash_search(self, query, page, per_page):
        r = self._unsplash_request("search/photos", {
            "query": query,
            "page": page,
            "per_page": per_page,
            "order_by": self.config["order_by"],
            "content_filter": self.config["content_filter"],
            "orientation": self.config["orientation"]
        })

        images = []
        for result in r.json()["results"]:
            images.append(UnsplashImage(result["id"], result["width"], result["height"], result["color"], result["user"]["username"], result["urls"]["raw"], result["links"]["html"]))

        return images

    def _collection_total_pages(self, collection_id):
        r = self._unsplash_request("collections/{}".format(collection_id), {})
        return math.ceil(r.json()["total_photos"] / self.config["max_per_page"])

    def _get_unsplash_collection(self, collection_id, page, per_page):
        r = self._unsplash_request("collections/{}/photos".format(collection_id), {
            "page": page,
            "per_page": per_page,
            "orientation": self.config["orientation"]
        })

        images = []
        for result in r.json():
            images.append(UnsplashImage(result["id"], result["width"], result["height"], result["color"], result["user"]["username"], result["urls"]["raw"], result["links"]["html"]))

        return images

    def add_search(self, query, total):
        total_pages = self._unsplash_search_total_pages(query)

        for i in range(math.ceil(total / self.config["max_per_page"])):
            page = random.randint(1, total_pages)
            print("getting page #" + str(page))

            self.download_queue += self._get_unsplash_search(query, page, self.config["max_per_page"])

    def add_collection(self, collection_id, total):
        total_pages = self._collection_total_pages(collection_id)

        for i in range(math.ceil(total / self.config["max_per_page"])):
            page = random.randint(1, total_pages)
            print("getting page #" + str(page))

            self.download_queue += self._get_unsplash_collection(collection_id, page, self.config["max_per_page"])

    def clear_downloads(self):
        print("clearing download directory")

        for filename in os.listdir(self.config["wallpaper_directory"]):
            os.unlink(os.path.join(self.config["wallpaper_directory"], filename))

    def download_images(self):
        with open(self.config["log_directory"] + time.strftime("%Y-%m-%d_%H-%M-%S") + ".json", "w") as log:
            log.write("[\n")

            for image in self.download_queue:
                log.write(str(image))
                log.write(",\n")

            log.write("]")

        print("downloading a total of {} images".format(len(self.download_queue)))

        def fetch_image(image: UnsplashImage):
            print("downloading wallpaper {}, {}".format(image.id, image.website))

            if not image.is_valid():
                print(f"unable to download '{image.id}': size is invalid")
                return

            image.download(self.config["wallpaper_directory"])

        results = ThreadPool(8).imap_unordered(fetch_image, self.download_queue)

        for error in results:
            if error:
                print(error)

        # for filename in os.listdir(self.config["wallpaper_directory"]):
        #     os.unlink(os.path.join(self.config["wallpaper_directory"], filename))

        # print("downloading a total of {} images".format(self.download_queue))

        # for i, image in enumerate(self.download_queue):
        #     print("#{} downloading wallpaper {}, {}".format(i, image.id, image.website))
        #     image.download(self.config["wallpaper_directory"])


if __name__ == "__main__":
    with open("./config.json5") as f:
        config = json5.load(f)

    downloader = UnsplashDownloader(config["downloader"])

    for query in config["querys"]:
        print(query)

        if query["type"] == "search":
            downloader.add_search(query["query"], query["page_count"])
        elif query["type"] == "collection":
            downloader.add_collection(query["collection_id"], query["page_count"])

    downloader.clear_downloads()
    downloader.download_images()
