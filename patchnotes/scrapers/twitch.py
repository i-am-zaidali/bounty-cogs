from .base import BaseScraper
import pyppeteer
from bs4 import BeautifulSoup
import semver
import datetime


class TwitchScraper(BaseScraper):

    def __init__(self, last_version: semver.Version):
        self.last_version = last_version

    async def get_patch_notes(self):
        browser = await pyppeteer.launch(
            options={
                # "headless": False,
                "executablePath": "/usr/bin/google-chrome",
            }
        )

        page = await browser.newPage()
        await page.goto(
            f"https://help.twitch.tv/s/article/patch-notes-{self.last_version.major+1}?language=en_US"
        )
        try:
            await page.waitForSelector(".section")

        except Exception as e:
            await browser.close()
            return self.last_version, "No patch notes found"
        enclosed = await page.evaluate(
            r"""() => {
                const article = document.querySelector("#article")
                let enclosed = []
                if (article !== null) {
                    const section = article.querySelector(".section");
                    if (section !== null) {
                        const ul = section.querySelector("ul");
                        enclosed.push(ul.outerHTML)
                    }
                }
                return enclosed
            }"""
        )

        enclosed = "".join(enclosed)
        await browser.close()
        soup = BeautifulSoup(enclosed, "html.parser")
        md = self.convert_element_to_md(soup)
        version = self.last_version.bump_major()
        return (
            version,
            f"# __TWITCH PATCH NOTES__ (VER: {self.last_version.bump_major()}) {datetime.datetime.now().strftime('%Y-%m-%d')}\n"
            + md,
        )
