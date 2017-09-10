import re

from misaka import Markdown, SaferHtmlRenderer


class Em2Markdown:
    def __init__(self):
        render = SaferHtmlRenderer(flags=('hard-wrap',))
        self.md = Markdown(render, extensions=('no-intra-emphasis',))

    def __call__(self, md_str):
        md_str = re.sub(r'\r\n', '\n', md_str)
        return self.md(md_str)


markdown = Em2Markdown()
