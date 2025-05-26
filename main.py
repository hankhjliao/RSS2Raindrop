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


class RSS:
    def __init__(self, rss_config_path="rss.yaml", rss_database_path="rss_database.zip", request_timeout=10.0):
        self.TOKEN = os.environ.get("TEST_TOKEN", None)
        self.url = "https://api.raindrop.io/rest/v1/raindrop"

        self.NOW = datetime.now()
        self.REQUEST_TIMEOUT = request_timeout
        self.rss_config_path = rss_config_path
        self.rss_database_path = rss_database_path
        self.rss_configs = None
        self.rss_database = pd.DataFrame(
            columns=[
                "feed_url",
                "saved_item_link_latest",
                "saved_item_link_second_latest",
                "updated_time",
            ]
        )

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
        ret = requests.post(self.url, data=json.dumps(data), headers=headers)
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

    def readRSSDatabase(self):
        if os.path.exists(self.rss_database_path):
            self.rss_database = pd.read_csv(self.rss_database_path)
        else:
            self.rss_database = pd.DataFrame(
                columns=[
                    "feed_url",
                    "saved_item_link_latest",
                    "saved_item_link_second_latest",
                    "updated_time",
                ]
            )

    def getLastTimeRSSData(self, rss_url):
        feed_location = self.rss_database["feed_url"] == rss_url
        idx = self.rss_database[feed_location].index.values[0]
        link_latest = self.rss_database.loc[idx, "saved_item_link_latest"]
        link_second_latest = self.rss_database.loc[idx, "saved_item_link_second_latest"]
        return idx, link_latest, link_second_latest

    def saveRSSDatabase(self):
        # Save the rss database
        archive_name = Path(self.rss_database_path).with_suffix(".csv").name
        self.rss_database.sort_values("feed_url").to_csv(archive_name, index=False)

        # This is for CLI user
        # As for GitHub Action user, the GitHub Action will compress the csv to zip
        # file when running upload-artifact
        with zipfile.ZipFile(self.rss_database_path, "w") as zf:
            zf.write("rss_database.csv")

    def run(self):
        # Iter all the feed configs
        for rss_config in self.rss_configs:
            # Get the feed config
            rss_url = rss_config["url"]
            rss_tags = rss_config.get("tags", ["feed"])
            rss_filter = rss_config.get("filter", "")
            rss_verify = rss_config.get("verify", True)
            rss_use_metadata = rss_config.get("use_metadata", False)

            # Get the feed content
            logging.info(f"Checking {rss_url}")
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

            # Check whether the feed is first run or not
            flag_first_run = False
            if rss_url not in self.rss_database["feed_url"].values:
                self.rss_database.loc[-1] = {
                    "feed_url": rss_url,
                    "saved_item_link_latest": None,
                    "saved_item_link_second_latest": None,
                    "updated_time": None,
                }
                self.rss_database.index = self.rss_database.index + 1
                flag_first_run = True

            # Get last time rss data
            idx, link_latest, link_second_latest = self.getLastTimeRSSData(rss_url)

            # Sort articles according to the published time
            try:
                articles = feed.get("entries", [])
                articles = sorted(articles, key=lambda e: e.published_parsed, reverse=True)
            except Exception as e:
                articles = feed.get("entries", [])
                logging.warning(f"Feed doesn't support published_parsed attribute: {rss_url}")

            # Iter articles in the feed
            for article in articles:
                # Break if the article is added before
                if (article.link == link_latest) or (article.link == link_second_latest):
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
                    if self.rss_database.loc[idx, "updated_time"] != self.NOW:
                        self.rss_database.loc[idx, "saved_item_link_second_latest"] = link_latest
                        self.rss_database.loc[idx, "saved_item_link_latest"] = article.link
                        self.rss_database.loc[idx, "updated_time"] = self.NOW
                else:
                    logging.warning(f"Article not added: {article.link}")

                # Add only one article when first run
                if flag_first_run:
                    break


if __name__ == "__main__":
    rss2pocket = RSS()
    rss2pocket.readRSSConfig()
    rss2pocket.readRSSDatabase()
    rss2pocket.run()
    rss2pocket.saveRSSDatabase()
