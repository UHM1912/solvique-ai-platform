import re
from typing import Optional

GREETINGS = {"hi", "hello", "hey", "hola", "yo", "sup", "howdy"}
GRATITUDE = {"thanks", "thank you", "thx", "ty", "thankyou", "thank u", "🙏"}
ACKNOWLEDGEMENTS = {"ok", "okay", "k", "cool", "nice", "great", "got it", "alright"}
FAREWELLS = {"bye", "goodbye", "good bye", "see you", "cya", "later", "take care"}
FILLER = {"test", "testing", "hello?", "are you there"}

_GIBBERISH_RE = re.compile(r"^[^a-zA-Z\u0900-\u097F]+$")
_REPEATED_RE = re.compile(r"^(.)\1{4,}$")


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def run_filter(user_input: str) -> Optional[str]:
    """Returns a response string if the query should be short-circuited, else None."""

    text = _normalize(user_input or "")

    if not text:
        return "Please type a question so I can help you."
    if _GIBBERISH_RE.match(text) or _REPEATED_RE.match(text):
        return "That doesn't look like a question. Try asking me something!"
    if text in GREETINGS:
        return "Hello! Ask me anything — I can query databases, search documents, and more."
    if text in GRATITUDE:
        return "You're welcome! Feel free to ask another question."
    if text in ACKNOWLEDGEMENTS:
        return "Got it! What would you like to query or explore next?"
    if text in FAREWELLS:
        return "Goodbye! Come back anytime you have a query."
    if text in FILLER:
        return "Hi there! Ask me anything and I'll find the answer for you."
    if len(text) < 6:
        return (
            "Could you elaborate? I need a bit more context to find the right answer."
        )

    return None
