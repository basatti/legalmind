import pathlib

path = pathlib.Path("src/graph/state.py")
text = path.read_text(encoding="utf-8")

addition = (
    "\n"
    "    should_continue: bool = False\n"
    '    """Set by the reason node: True sends the run back to retrieve for\n'
    "    another pass, False lets it fall through to answer. LEG-78. Read once by\n"
    "    the graph's conditional edge after reason, never by reason itself on a\n"
    "    later call - the node decides fresh each time from state.iterations and\n"
    '    what it just read, not from what it decided last time."""\n'
)

text = text.rstrip("\n") + "\n" + addition
path.write_text(text, encoding="utf-8", newline="\n")
print("Done.")
