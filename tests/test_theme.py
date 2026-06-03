from app import theme
from app.models import Paper


class FakeMessage:
    def __init__(self, text):
        self.content = [type("B", (), {"text": text})()]


class FakeClient:
    def __init__(self, text="Gene editing"):
        self._text = text
        self.messages = self

    def create(self, **kwargs):
        self.kwargs = kwargs
        return FakeMessage(self._text)


def test_tag_theme_sets_theme(paper):
    client = FakeClient("Graphene science")
    theme.tag_theme(paper, client)
    assert paper.theme == "Graphene science"


def test_tag_theme_uses_abstract_in_prompt(paper):
    client = FakeClient()
    theme.tag_theme(paper, client)
    content = client.kwargs["messages"][0]["content"]
    assert "graphene synthesis" in content.lower()


def test_tag_theme_skips_when_empty():
    p = Paper(openalex_id="W", doi=None, title=None, abstract=None, content=None)
    client = FakeClient()
    theme.tag_theme(p, client)
    assert p.theme is None
