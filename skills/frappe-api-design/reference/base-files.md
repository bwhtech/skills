# The base layer

Four things an app needs once, before any domain package exists. Substitute the app's module
name for `<app>` and its PascalCase name for `<App>`; nothing else changes.

## Check pydantic first

The base schemas import pydantic. Frappe bundles it, so most apps get it for free and never
declare it — confirm on the target bench before relying on that:

```bash
bench --site <site> console
>>> import pydantic; pydantic.VERSION
```

If that fails, add `"pydantic~=2.0"` to `dependencies` in the app's `pyproject.toml`.

## `hooks.py`

```python
# Require all whitelisted methods to have type annotations
require_type_annotated_api_methods = True
```

Frappe then rejects an unannotated whitelisted argument at runtime rather than coercing it.
Set this before writing endpoints — turning it on later means fixing every existing one at
once.

## `<app>/api/schemas.py`

```python
from pydantic import BaseModel, ConfigDict


class APIRequest(BaseModel):
	model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class APIResponse(BaseModel):
	model_config = ConfigDict(extra="forbid")

	def __json__(self) -> dict:
		# frappe's json_handler checks __json__ before its Iterable branch; without this a
		# BaseModel serializes as a list of (key, value) pairs.
		# Not model_dump(): frappe._dict answers every attribute lookup via dict.get, so
		# pydantic mistakes untyped rows for models carrying a None serializer and dies.
		return {name: jsonify_value(getattr(self, name)) for name in type(self).model_fields}


def jsonify_value(value):
	if isinstance(value, APIResponse):
		return value.__json__()
	if isinstance(value, list):
		return [jsonify_value(item) for item in value]
	return value
```

Keep both comments. They are the reason the method is written this way, and the failure they
describe (`"'None' is not an instance of SchemaSerializer"`) is opaque enough that someone
will otherwise "simplify" this to `model_dump()` and rediscover it.

The asymmetry between the two `model_config`s is deliberate: requests ignore extra keys so an
older client keeps working, responses forbid them so a typo in a field name fails loudly
instead of shipping a key nothing reads.

## `<app>/api/exceptions.py`

```python
from typing import NoReturn

import frappe
from frappe import _lt


class <App>APIError(frappe.ValidationError):
	"""Base for API errors.

	`http_status_code` is read by frappe.app.handle_exception. `title` and `message` are
	declared with `_lt` so they are translated per request rather than at import, and reach
	the client as `_server_messages`, which is what `err.messages[0]` renders.

	Raise via `throw()`, never `raise SomeError` — a bare raise skips msgprint, leaving the
	client to fall back to "Internal Server Error".
	"""

	http_status_code = 400
	title = _lt("Error")
	message = _lt("Something went wrong. Please try again.")

	@classmethod
	def throw(cls, **context) -> NoReturn:
		message = str(cls.message)
		frappe.throw(message.format(**context) if context else message, cls, title=str(cls.title))


class ResourceNotFound(<App>APIError):
	http_status_code = 404
	title = _lt("Not Found")
	message = _lt("The record you are looking for does not exist.")


class NotPermitted(<App>APIError):
	http_status_code = 403
	title = _lt("Not Permitted")
	message = _lt("You do not have permission to do this.")


class Conflict(<App>APIError):
	http_status_code = 409
	title = _lt("Not Allowed")
	message = _lt("This action conflicts with the current state of the record.")
```

Subclassing `frappe.ValidationError` rather than `Exception` keeps every existing
`except frappe.ValidationError` handler in the app working.

Four classes is the whole hierarchy. Domains subclass these; nothing else gets added here.

## `<app>/api/test_exceptions.py`

This one is not optional. Without it the `throw()`-versus-`raise` distinction is a comment,
and comments do not fail CI.

```python
import frappe
from frappe import _lt
from frappe.tests import IntegrationTestCase

from <app>.api.exceptions import <App>APIError, Conflict, NotPermitted, ResourceNotFound


class Parameterized(<App>APIError):
	http_status_code = 418
	title = _lt("Teapot")
	message = _lt("{item} is not available.")


class Test<App>APIError(IntegrationTestCase):
	def setUp(self):
		frappe.clear_messages()

	def last_message(self) -> dict:
		return frappe.local.message_log[-1]

	def test_throw_raises_its_own_class(self):
		with self.assertRaises(Conflict):
			Conflict.throw()

	def test_throw_publishes_title_and_message(self):
		with self.assertRaises(Conflict):
			Conflict.throw()

		self.assertEqual(self.last_message()["title"], "Not Allowed")
		self.assertIn("conflicts", self.last_message()["message"])

	def test_message_accepts_context(self):
		with self.assertRaises(Parameterized):
			Parameterized.throw(item="Chai")

		self.assertEqual(self.last_message()["message"], "Chai is not available.")

	def test_bare_raise_publishes_nothing(self):
		# A bare raise skips msgprint, so the client would show "Internal Server Error".
		with self.assertRaises(Conflict):
			raise Conflict

		self.assertEqual(frappe.local.message_log, [])

	def test_status_codes(self):
		self.assertEqual(<App>APIError.http_status_code, 400)
		self.assertEqual(ResourceNotFound.http_status_code, 404)
		self.assertEqual(NotPermitted.http_status_code, 403)
		self.assertEqual(Conflict.http_status_code, 409)

	def test_subclass_inherits_status_code(self):
		self.assertEqual(Parameterized.http_status_code, 418)

	def test_errors_are_validation_errors(self):
		# Keeps existing `except frappe.ValidationError` handlers working.
		self.assertTrue(issubclass(<App>APIError, frappe.ValidationError))
```

## Verify the bootstrap

```bash
bench --site <site> run-tests --module <app>.api.test_exceptions
```

Eight passing tests means the base layer is wired: status codes reach
`handle_exception`, `throw()` publishes to the message log, and a bare `raise` demonstrably
does not.
