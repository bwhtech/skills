---
name: frappe-api-design
description: How to build whitelisted HTTP APIs in a Frappe app — the <app>/api/<domain>/ package layout, pydantic request/response schemas, a status-carrying error hierarchy, service classes, and the frappe.whitelist conventions (type annotations, methods=["POST"], allow_guest). Use when writing a new endpoint under <app>/api/ with its response payload, error classes, service and tests, and when the user says "add an API", "new endpoint", "whitelisted method", "expose X to the frontend", or "the client needs data for X".
---

# Building APIs in a Frappe app

Every call from a frontend client lands on a `@frappe.whitelist()` function. The URL *is* the
dotted module path (`myapp.api.tickets.get_ticket_details`), so **the file layout is the public
API surface** — that's why it's organised by domain and why endpoint names never change
casually. Renaming a module breaks callers exactly as renaming a REST route would.

## Bootstrap

An app adopting this needs `<app>/api/schemas.py`, `<app>/api/exceptions.py`, their test, and
one `hooks.py` flag. `reference/base-files.md` has all four ready to paste — substitute the
app name and nothing else. Do that first; the rest of this skill assumes those exist.

In an app that already has them, match what's there. Where existing code under `<app>/api/`
disagrees with this skill, it predates the convention — it is not the pattern to copy, and
it's not yours to migrate unless asked.

## Package layout

One package per domain, each file with one job:

```
<app>/api/<domain>/
  __init__.py      endpoints only — decorate, delegate, return
  services.py      the work: service class and/or module functions
  schemas.py       pydantic request/response models
  exceptions.py    named error classes
  test_<domain>.py IntegrationTestCase tests
```

A domain is a noun the product already uses — `tickets`, `booking`, `checkin` — not a
technical layer. Split further when a file passes ~300 lines: a large `booking` package
earns `guests.py`, `coupons.py`, `details.py` alongside its `services.py`.

Not every file is mandatory. A domain thin enough that a service layer would be an empty hop
— endpoints that call frappe directly and return, like a login-context or payment-callback
domain — gets no `services.py`. Don't add one for symmetry.

## The endpoint

Endpoints are one to three lines. They validate by annotation, delegate, and return:

```python
@frappe.whitelist()
def get_ticket_details(ticket_id: str) -> TicketDetailsResponse:
	return services.TicketService(ticket_id).details()
```

Rules that are load-bearing, not style:

- **Annotate every argument.** With `require_type_annotated_api_methods = True` set, frappe
  rejects an unannotated whitelisted argument at runtime instead of coercing it. Annotate the
  return type too — with a response model it doubles as the payload contract.
- **Anything that writes takes `methods=["POST"]`.** Frappe skips CSRF validation outside
  `UNSAFE_HTTP_METHODS` and only auto-commits on POST/PUT, so a write reachable over GET is
  both unprotected and silently rolled back. Leave reads unrestricted — pinning their verb
  only risks a caller.
- **Permission checks belong in the service, not the endpoint** — in the one function every
  caller routes through. The recurring bug is a guard that sits in one endpoint while a
  sibling endpoint reaches the same data through a shared builder that has no check at all.
- **Don't whitelist internals.** Lifecycle hooks (`after_insert`) become remotely
  re-runnable through `run_doc_method`. A service function like `get_payment_link_for_booking`
  lets a client name its own amount source. If nothing calls it over HTTP, it isn't an
  endpoint.

`allow_guest=True` widens the surface to the whole internet. Anything behind it that costs
something per call — sending mail or SMS, hitting a paid third party — takes a `rate_limit`,
keyed on whatever identifies the caller:

```python
@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="identifier", limit=5, seconds=3600)
def send_guest_booking_otp(event: int, identifier: str) -> dict | None:
	return guests.send_booking_otp(event, identifier)
```

If the app runs [frappe-semgrep-rules](https://github.com/frappe/semgrep-rules) in CI, each
guest endpoint also needs
`# nosemgrep: frappe-semgrep-rules.rules.security.guest-whitelisted-method` — trailing when
the decorator is short, on its own line above it when the decorator is doing more than one
thing. The comment is an assertion that a human considered the exposure; add it when you have,
not to quiet the build.

## Schemas

`<app>/api/schemas.py` holds the two bases. Requests extend `APIRequest` (`extra="ignore"`,
whitespace stripped), responses extend `APIResponse` (`extra="forbid"`).

```python
class TicketAddOnDetail(APIResponse):
	id: str
	title: str | None
	price: float | None
	options: list[str]
```

The response model replaces hand-built dicts, so the wire shape is the type signature. Two
things to know:

- **`APIResponse.__json__` returns raw field values on purpose** and deep-converts only
  nested `APIResponse` models. It does not call `model_dump()`: `frappe._dict.__getattr__` is
  `dict.get`, so pydantic mistakes an untyped row for a model carrying a `None` serializer and
  raises `"'None' is not an instance of SchemaSerializer"`. Documents and query rows are left
  to frappe's `json_handler`, as before.
- **Whole documents and meta-shaped rows stay `Any` / `list`**, with a one-line comment saying
  why. Typing a document would reshape a payload the client already reads, field by field.
  Rows from a fixed `get_all` field list, on the other hand, get a real model — you already
  know every key.

A pydantic model *as a parameter* reshapes the wire payload: the client has to nest its body
under the parameter name (`{"booking": {...}}`). Worth it for something that otherwise takes
sixteen flat arguments; not worth it for two. Keys defined dynamically at runtime — per-event
custom fields, per-form questions — stay `list[dict]`: link values arrive as ints, and typing
them makes frappe's argument validation reject the payload.

When a payload changes shape, the client's data layer changes with it in the same commit.
Grep the frontend source for the endpoint path before you consider the change done.

## Errors

`<app>/api/exceptions.py` has the base and three status-carrying subclasses: `<App>APIError`
(400), `ResourceNotFound` (404), `NotPermitted` (403), `Conflict` (409). Each domain's
`exceptions.py` subclasses those and declares its own:

```python
class TransferWindowClosed(Conflict):
	title = _lt("Transfers Closed")
	message = _lt("The transfer window for this event has closed.")
```

```python
TransferWindowClosed.throw()
TicketNotInBooking.throw(ticket_id=ticket_id, booking_id=booking_id)  # message.format(**context)
```

- **`_lt`, not `_`** — class bodies run at import, before a request has a language. The
  translation extractor already scans `_lt`.
- **`throw()`, never `raise SomeError`.** `throw()` routes through `frappe.throw` so the text
  reaches `_server_messages`, which is what a frappe-ui client renders as `err.messages[0]`.
  A bare raise skips msgprint and leaves the user staring at "Internal Server Error". The
  bootstrap test keeps that distinction visible.
- **A class per condition the user can hit differently**, not one per throw site. Four named
  errors for a booking flow, not fourteen; generic internal failures keep a plain
  `frappe.throw`.
- **Leave frappe's own errors alone** when they already carry the right status and a clear
  message — `DoesNotExistError` on an unknown record, `AuthenticationError` for login. Wrap
  one only when the client branches on `exc_type`, and then move both sides in the same
  commit.
- Site misconfiguration — a missing optional app, an unset setting — stays 4xx. A 5xx writes
  an Error Log on every click.

## Services

Reach for a class when there's per-request state, which usually means one document. The id
goes in the constructor along with the cheap guards; the document is a plain property:

```python
class CheckinService:
	"""Check in a single ticket at the door. Restricted to Ticket Agent."""

	def __init__(self, ticket_id: str):
		frappe.only_for("Ticket Agent", True)
		if not frappe.db.exists("Event Ticket", ticket_id):
			TicketNotFound.throw()
		self.ticket_id = ticket_id

	@property
	def ticket(self) -> "EventTicket":
		return frappe.get_cached_doc("Event Ticket", self.ticket_id)
```

- **Plain property, not `cached_property`.** `get_cached_doc` already caches; a second layer
  only adds one that can go stale inside a request.
- **Import doctype controllers under `TYPE_CHECKING`** for those return annotations — no
  runtime import, so no import cycle through controllers that import from `<app>.api`.
- **List queries and cross-doctype operations stay module functions.** A class with a single
  method is ceremony.
- Keep methods near ten lines; a long `process()` reads as a sequence of named steps
  (`validate_event`, `build_booking`, `finalize`).
- Batch per-row lookups into maps instead of a `get_value` per row. Watch key types when you
  do: a doctype that autonames to integers still arrives as a string through a Link field, so
  map keys need an explicit `str()` — the SQL those lookups replace was coercing silently.
- `frappe.parse_json`, not `json.loads` — it already returns a `frappe._dict` for dicts.
- A manual `frappe.db.commit()` needs a reason in a comment, and the
  `# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit` marker where that ruleset
  runs.

## Tests

`test_<domain>.py` in the domain package, `IntegrationTestCase`, **importing the endpoints
rather than the services** so the whitelisted surface is what's covered. Assert on the error
classes: `with self.assertRaises(TransferWindowClosed)`.

```bash
bench --site <site> run-tests --module <app>.api.tickets.test_tickets
```

Two traps that cost real debugging time:

- **Own your fixtures.** `IntegrationTestCase` rolls the database back but not the document
  cache. A test that mutates a shared record leaves the cache holding a value the rollback has
  since removed from the row — visible to every later test module in the same process. Create
  your own records rather than editing shared ones.
- **Singles can't be owned**, so drop them from the cache instead:
  `self.addCleanup(frappe.clear_document_cache, "My Settings", "My Settings")`.
- `frappe.clear_messages()` in `setUp` if you assert on `frappe.local.message_log`.

Cover the payload key set when a response shape matters. Add a browser test when the behaviour
is one only a browser can catch — a client-side role gate, an `exc_type` branch, keys a
component renders.
