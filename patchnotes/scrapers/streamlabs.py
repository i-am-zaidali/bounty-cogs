from .base import BaseScraper
from bs4 import BeautifulSoup
import pyppeteer
import semver
import datetime


class StreamlabsScraper(BaseScraper):
    async def get_patch_notes(self):
        browser = await pyppeteer.launch(
            options={
                # "headless": False,
                "executablePath": "/usr/bin/google-chrome",
            }
        )

        page = await browser.newPage()
        await page.goto(
            "https://streamlabs.com/content-hub/post/streamlabs-desktop-patch-notes",
            options={"waitUntil": "domcontentloaded", "timeout": 0},
        )
        await page.waitForSelector(".article__post")
        enclosed = await page.evaluate(
            r"""() => {
                const articleText = document.querySelector(".article__post")
                let enclosed = []
                if (articleText !== null) {
                    const hr = articleText.querySelector("hr");
                    if (hr !== null) {
                        let currentNode = hr.nextElementSibling;
                        while (!currentNode.isEqualNode(hr)) {
                            enclosed.push(currentNode.outerHTML);
                            currentNode = currentNode.nextElementSibling;
                        }
                    }
                }
                return enclosed
            }"""
        )

        await browser.close()

        soup = BeautifulSoup("".join(enclosed), "html.parser")
        md = self.convert_element_to_md(soup)
        version = semver.Version.parse(
            getattr(self.version_re.search(md), "group", lambda x: "1.0.0")(0), True
        )
        return (
            version,
            f"# __STREAMLABS PATCH NOTES__ (VER: {version}) {datetime.datetime.now().strftime('%Y-%m-%d')}\n"
            + md,
        )
