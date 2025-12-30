from etl.crawler import parse_verses

def test_etl_smoke_with_sample_html():
    html = """
    <div id="tdBible1" class="bible_read">
      <span>
        <span class="number">1</span>
        <font class="area">태초에</font>
        <font class="area">하나님이</font>
      </span>
    </div>
    """

    verses = parse_verses(html)

    assert verses == [(1, "태초에 하나님이")]

