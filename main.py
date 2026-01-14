import argparse
import json
import logging
import os
import zipfile

import feedparser
import pandas as pd
import requests
import yaml

from datetime import datetime
from io import BytesIO
from pathlib import Path

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)


class RSSDatabase:
    def __init__(self, rss_database_path=""):
        self.VERSION = "2.0.0"
        self.NOW = datetime.now()

        self.rss_database_path = rss_database_path
        self.rss_database_saved_item_link_columns = [f"saved_item_link_latest_{i}" for i in range(10)]
        self.rss_database_saved_item_link_columns_len = len(self.rss_database_saved_item_link_columns)
        self.rss_database_columns = [
            "feed_url",
            *self.rss_database_saved_item_link_columns,
            "updated_time",
            "rss_database_version",
        ]
        self.rss_database = pd.DataFrame(columns=self.rss_database_columns)

        if self.rss_database_path != "":
            self.read()

    def isCompatible(self):
        if len(self.rss_database.index) == 0:
            return False

        if "rss_database_version" not in self.rss_database.columns:
            version = "1.0.0"
        else:
            idx = self.rss_database["rss_database_version"].first_valid_index()
            if idx is not None:
                version = self.rss_database["rss_database_version"].loc[idx]
            else:
                version = "1.0.0"

        class_version = list(map(int, self.VERSION.split(".")))
        version = list(map(int, version.split(".")))
        return class_version[0] == version[0]

    def read(self, rss_database_path=""):
        if rss_database_path == "":
            rss_database_path = self.rss_database_path

        self.rss_database_path = rss_database_path
        if os.path.exists(self.rss_database_path):
            self.rss_database = pd.read_csv(self.rss_database_path)
            if not self.isCompatible():
                self.rss_database = pd.DataFrame(columns=self.rss_database_columns)
        else:
            self.rss_database = pd.DataFrame(columns=self.rss_database_columns)

    def save(self, rss_database_path=""):
        if rss_database_path == "":
            rss_database_path = self.rss_database_path

        # Save the rss database
        archive_name = Path(rss_database_path).with_suffix(".csv").name
        self.rss_database.sort_values("feed_url").to_csv(archive_name, index=False)

        # This is for CLI user
        # As for GitHub Action user, the GitHub Action will compress the csv to zip
        # file when running upload-artifact
        with zipfile.ZipFile(Path(rss_database_path).with_suffix(".zip").name, "w") as zf:
            zf.write(str(archive_name))

    def add(self, key):
        if key not in self.rss_database["feed_url"].values:
            rss_database_item = {}
            for column in self.rss_database_columns:
                rss_database_item[column] = None
            rss_database_item["feed_url"] = key
            rss_database_item["rss_database_version"] = self.VERSION

            self.rss_database.loc[-1] = rss_database_item
            self.rss_database.index = self.rss_database.index + 1

    def update(self, key, article_link):
        if key not in self.rss_database["feed_url"].values:
            return
        feed_location = self.rss_database["feed_url"] == key
        idx = self.rss_database[feed_location].index.values[0]
        if self.rss_database.loc[idx, "updated_time"] != self.NOW:
            for i in range(self.rss_database_saved_item_link_columns_len - 1):
                column_from = self.rss_database_saved_item_link_columns[-i - 2]
                column_to = self.rss_database_saved_item_link_columns[-i - 1]
                self.rss_database.loc[idx, column_to] = self.rss_database.loc[idx, column_from]
            self.rss_database.loc[idx, self.rss_database_saved_item_link_columns[0]] = article_link
            self.rss_database.loc[idx, "updated_time"] = self.NOW
            self.rss_database.loc[idx, "rss_database_version"] = self.VERSION

    def get(self, key):
        if key not in self.rss_database["feed_url"].values:
            return []
        feed_location = self.rss_database["feed_url"] == key
        idx = self.rss_database[feed_location].index.values[0]
        links = []
        for column in self.rss_database_saved_item_link_columns:
            links.append(self.rss_database.loc[idx, column])
        return links


class RSS:
    def __init__(self, rss_config_path="rss.yaml", rss_database_path="rss_database.zip", request_timeout=10.0):
        self.TOKEN = os.environ.get("TEST_TOKEN", None)
        self.URL = "https://api.raindrop.io/rest/v1/raindrop"

        self.REQUEST_TIMEOUT = request_timeout
        self.rss_config_path = rss_config_path
        self.rss_configs = None
        self.rss_database = RSSDatabase(rss_database_path)

    def addArticle(self, article_url, article_metadata=None, tags=[]):
        tags.append("feed")
        data = {
            "link": article_url,
            "tags": tags,
        }
        if article_metadata is None:
            data["pleaseParse"] = {}
        else:
            data["title"] = article_metadata["title"]
        headers = {
            "Authorization": f"Bearer {self.TOKEN}",
            "Content-Type": "application/json",
        }
        ret = requests.post(self.URL, data=json.dumps(data), headers=headers)
        ret = json.loads(ret.text)
        if ret.get("result", None) is None:
            logging.error(ret)
            return False
        return ret["result"]

    def readRSSConfig(self):
        if os.path.exists(self.rss_config_path):
            with open(self.rss_config_path, "r") as stream:
                try:
                    self.rss_configs = yaml.safe_load(stream)
                except Exception as e:
                    logging.error(f"Unexpected error when parsing yaml: {str(e)}")
                    exit()
        else:
            logging.error(f"{self.rss_config_path} not exists.")
            exit()

    def run(self):
        # Iter all the feed configs
        for rss_config in self.rss_configs:
            # Get the feed config
            rss_url = rss_config["url"]
            rss_tags = rss_config.get("tags", ["feed"])
            rss_filter = rss_config.get("filter", "")
            rss_verify = rss_config.get("verify", True)
            rss_use_metadata = rss_config.get("use_metadata", False)
            rss_sort_key = rss_config.get("sort_key", "published_parsed")

            # Get the feed content
            logging.info(f"Checking {rss_config}")
            try:
                resp = requests.get(rss_url, timeout=self.REQUEST_TIMEOUT, verify=rss_verify)
            except requests.ReadTimeout:
                logging.warning(f"Timeout when reading feed: {rss_url}")
                continue
            except requests.ConnectionError:
                logging.warning(f"Cannot access feed: {rss_url}")
                continue
            except Exception as e:
                logging.error(f"Unexpected error: {str(e)}")
                continue
            content = BytesIO(resp.content)
            feed = feedparser.parse(content)

            # Get last time rss data
            flag_first_run = False
            added_links = self.rss_database.get(rss_url)
            if len(added_links) == 0:
                self.rss_database.add(rss_url)
                flag_first_run = True

            # Sort articles according to the published time
            try:
                articles = feed.get("entries", [])
                if rss_sort_key == "link":
                    articles = sorted(articles, key=lambda e: e.link, reverse=True)
                else:
                    articles = sorted(articles, key=lambda e: e.published_parsed, reverse=True)
            except Exception as e:
                articles = feed.get("entries", [])
                logging.warning(f"Feed doesn't support published_parsed attribute: {rss_url}")

            # Iter articles in the feed
            for article in articles:
                # Break if the article is added before
                if article.link in added_links:
                    break

                # Print article information
                article_published_time = article.get("published", None)
                logging.info(f"Article Info:\n\tTitle: {article.title}\n\tPublished time: {article_published_time}\n\tLink: {article.link}")

                if rss_use_metadata:
                    article_metadata = {"title": article.title}
                else:
                    article_metadata = None

                # Add the article
                if self.addArticle(article.link, article_metadata, rss_tags):
                    logging.info("Article added")

                    # Update the rss database
                    self.rss_database.update(rss_url, article.link)
                else:
                    logging.warning(f"Article not added: {article.link}")

                # Add only one article when first run
                if flag_first_run:
                    break


if __name__ == "__main__":
    rss2pocket = RSS()
    rss2pocket.readRSSConfig()
    rss2pocket.run()
    rss2pocket.rss_database.save()
