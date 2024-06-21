import semver
import re
from pathlib import Path
import os
import mimetypes


class BaseScraper:
    # regex stolen from semver
    version_re = re.compile(
        r"""\b(?P<major>(?:0|[1-9][0-9]*))\.(?P<minor>(?:0|[1-9][0-9]*))\.?(?P<patch>(?:0|[1-9][0-9]*))?(\-(?P<prerelease>(?:0|[1-9A-Za-z-][0-9A-Za-z-]*)(\.(?:0|[1-9A-Za-z-][0-9A-Za-z-]*))*))?(\+(?P<build>[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*))?\b""",
        flags=re.RegexFlag.M | re.RegexFlag.I,
    )

    def __init__(self, *args, **kwargs):
        super().__init__()

    @staticmethod
    def is_executable(file_path: Path):
        # Check permissions (Unix-based)
        if not file_path.is_file():
            # print(f"{file_path} is not a file")
            return False

        is_exec = os.access(file_path, os.X_OK)
        # print(f"{file_path} is executable: {is_exec=}")

        # Check MIME type (Cross-platform)
        mime_type, _ = mimetypes.guess_type(str(file_path))
        is_exec_mime = mime_type in [
            "application/x-executable",
            "application/x-msdos-program",
            "application/octet-stream",
            "application/x-shellscript",
        ]
        # print(f"{file_path} is executable (MIME): {is_exec_mime=} {mime_type=}")

        extension = file_path.suffix or ""
        is_exe = extension.lower() in [
            ".exe"
        ]  # , ".bat", ".cmd", ".com"] # we don't need these lol
        # print(f"{file_path} is executable (extension): {is_exe=}")

        return (
            is_exec
            or (is_exec_mime and is_exe)
            or ((f := open(file_path, "rb")).read(2).startswith(b"MZ"), f.close())[0]
        )

    def convert_element_to_md(self, element, level=-1) -> str:
        if isinstance(element, str):
            return element
        elif element.name is None:
            return element.string or ""
        else:
            result = ""
            for child in element.children:
                result += self.convert_element_to_md(child, level + 1)
            return self._format_tag_to_discord_md(element, result, level)

    def _format_tag_to_discord_md(self, tag, content: str, level=0):
        if tag.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            return f"{'#' * int(tag.name[1])} {content}\n"
        elif tag.name == "a":
            if content.strip() == tag["href"].strip():
                return f"<{content}>"
            return f"[{content}](<{tag['href']}>)"
        elif tag.name == "img":
            return f"![{tag['alt']}](<{tag['src']}>)"
        elif tag.name == "ul":
            return self._ul_to_md(tag, level)
        elif tag.name == "ol":
            return self._ol_to_md(tag, level)
        elif tag.name in ["strong", "bold", "b"]:
            return f"**{content}**"
        elif tag.name == "code":
            return f"```\n{content}\n```"
        elif tag.name == "div":
            if "markdown-alert-note" in tag.get("class", []):
                return f"**Note:** __{content.replace('Note', '', 1)}__"
            elif "markdown-alert-important" in tag.get("class", []):
                return f"**Important:** __{content.replace('Important', '', 1)}__"
        return content

    def _ul_to_md(self, tag, level=0) -> str:
        final_md: str = ""
        for el in tag.children:
            if el.name == "li":
                tab = "  " * level
                final_md += f"{tab}- {self.convert_element_to_md(el, level+1)}\n"
            elif el.name == "ul":
                nested_list = self._ul_to_md(el, level + 1)
                final_md += nested_list
        return final_md

    def _ol_to_md(self, tag, level=0) -> str:
        final_md = ""
        for el in tag.children:
            if el.name == "li":
                tab = "  " * level
                final_md += f"{tab}1. {self.convert_element_to_md(el, level+1)}\n"
            elif el.name == "ol":
                nested_list = self._ol_to_md(el, level + 1)
                final_md += nested_list
        return final_md

    async def get_patch_notes(self) -> tuple[semver.Version, str]:
        raise NotImplementedError
