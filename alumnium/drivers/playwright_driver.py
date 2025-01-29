import logging
from contextlib import contextmanager
from base64 import b64encode
from playwright.sync_api import Page, Error

from alumnium.aria import AriaTree
from .keys import Key
from .base_driver import BaseDriver

logger = logging.getLogger(__name__)

class PlaywrightDriver(BaseDriver):
    CANNOT_FIND_NODE_ERROR = "Could not find node with given id"
    NOT_SELECTABLE_ERROR = "Element is not a <select> element"
    CONTEXT_WAS_DESTROYED_ERROR = "Execution context was destroyed"

    def __init__(self, page: Page):
        self.client = page.context.new_cdp_session(page)
        self.page = page

    @property
    def aria_tree(self) -> AriaTree:
        self.wait_for_page_to_load()
        return AriaTree(self.client.send("Accessibility.getFullAXTree"))

    def click(self, id: int):
        with self._find_element(id) as element:
            tag_name = element.evaluate("el => el.tagName").lower()
            # Llama often attempts to click options, not select them.
            if tag_name == "option":
                element.locator("xpath=.//parent::select").select_option(element.text_content())
            else:
                element.click()

    def drag_and_drop(self, from_id: int, to_id: int):
        with self._find_element(from_id) as from_element:
            with self._find_element(to_id) as to_element:
                from_element.drag_to(to_element)

    def hover(self, id: int):
        with self._find_element(id) as element:
            element.hover()

    def press_key(self, key: Key):
        self.page.keyboard.press(key.value)

    def quit(self):
        self.page.close()

    @property
    def screenshot(self) -> str:
        return b64encode(self.page.screenshot()).decode()

    def select(self, id: int, option: str):
        with self._find_element(id) as element:
            tag_name = element.evaluate("el => el.tagName").lower()
            # Anthropic chooses to select using option ID, not select ID
            if tag_name == "option":
                element.locator("xpath=.//parent::select").select_option(option)
            else:
                element.select_option(option)

    @property
    def title(self) -> str:
        return self.page.title()

    def type(self, id: int, text: str):
        with self._find_element(id) as element:
            element.fill(text)

    @property
    def url(self) -> str:
        return self.page.url

    @contextmanager
    def _find_element(self, id: int):
        # Beware!
        self.client.send("DOM.enable")
        self.client.send("DOM.getFlattenedDocument")
        node_ids = self.client.send("DOM.pushNodesByBackendIdsToFrontend", {"backendNodeIds": [id]})
        node_id = node_ids["nodeIds"][0]
        self.client.send(
            "DOM.setAttributeValue",
            {
                "nodeId": node_id,
                "name": "data-alumnium-id",
                "value": str(id),
            },
        )
        yield self.page.locator(f"css=[data-alumnium-id='{id}']")
        try:
            self.client.send(
                "DOM.removeAttribute",
                {
                    "nodeId": node_id,
                    "name": "data-alumnium-id",
                },
            )
        except Error as error:
            # element can be removed by now
            if self.CANNOT_FIND_NODE_ERROR in error.message:
                pass
            else:
                raise error

    def wait_for_page_to_load(self):
        logger.info(f"Waiting for page to finish loading")
        with open("./scripts/waiter.js") as f:
            waiter_script = f.read()
        with open("./scripts/waitFor.js") as f:
            wait_for_script = f"(...scriptArgs) => new Promise((resolve) => {{ const arguments = [...scriptArgs, resolve]; {f.read()} }})"

        try:
            self.page.evaluate(f"function() {{ {waiter_script} }}")
            error = self.page.evaluate(wait_for_script)
            if error is not None:
                logger.info(f"Failed to wait for page to load: {error}")
        except Error as error:
            if self.CONTEXT_WAS_DESTROYED_ERROR in error.message:
                logger.info(f"Failed to wait for page to load: {error}")
            else:
                raise error
