<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/astabuzz-logo.webp">
    <img src="assets/astabuzz-logo-blue.webp" width="420" alt="astabuzz">
  </picture>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.0.1-green" alt="Version">
  <img src="https://img.shields.io/badge/python-≥3.14-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/uv-managed-purple?logo=astral&logoColor=white" alt="uv">
  <img src="https://img.shields.io/badge/license-MIT-yellow" alt="MIT License">
</p>

<p align="center">
  <strong><em>Il buzzer dell'asta del Fantacalcio.<br>Ovunque, da qualsiasi dispositivo.</em></strong><br><br>
  A digital FantaBuzzer button, for the friend who can't be at the table
  or for everyone in the room who doesn't have one.
</p>

<p align="center">
  <img src="assets/buttons-row.webp" width="640" alt="The eight buttons">
</p>

---

> ### ⚠️ Unofficial and experimental
>
> This is a **unofficial** hobby project. It is **not** produced,
> published, endorsed, sponsored or supported by FantaBuzzer®, Fantacalcio®,
> Quadronica or anyone connected to them, and it is not affiliated with them in
> any way. Their names appear here only to say which hardware this works with.
>
> It is also **experimental**: written for one lega's auction, tested on one
> Macbook, and offered as-is with no warranty and no support. If it misfires during
> your asta, [open an issue](../../issues).
>
> Buy the real thing from the people who made it:
> [fantabuzzer.com](https://www.fantabuzzer.com/).

## What this is

A toy project, made by a fantacalcio player for fantacalcio players — the kind
who spend eleven months waiting for one evening in August.

The [FantaBuzzer](https://www.fantabuzzer.com/) team built a genuinely lovely
thing: chunky USB buttons that turn the asta into a game show, and
[FantaAsta Buzz](https://www.fantacalcio.it/app-fantaasta-buzz) to run it. It is
well made and it works. It is also, by design, for people **in the same room** —
their FAQ says so plainly.

Our lega had one member playing from another city. So I took the buttons apart
(figuratively), worked out how they talk to the computer, and wrote a small web
app that presses them from a phone.

**It turns out the buttons are just USB keyboards.** Each one types a single
letter: P1 types `a`, P2 types `b`, and so on to P8 and `h`. That's the whole
trick. No driver, no protocol, no magic — so a remote press is nothing more than
that same letter, typed on the host PC. FantaAsta Buzz can't tell the
difference, because there isn't one.

Two things you can do with it:

- **Play from far away.** One link, one PIN, and your friend in another city
  buzzes like everyone else.
- **Play in the same room without enough buttons.** A kit has eight. If you're
  ten, the two without a button open the page on their phone and they're in.

## How it feels to use

Open the link, type the PIN, tap your number once. After that it's just a big
button.

Your number is remembered, so a refresh in the middle of the asta doesn't lose
your place. Presses carry the same 800 ms cooldown the real buttons have, so
nobody can machine-gun a bid, and every press confirms on screen — a press that
didn't land never looks like one that did.

## What you need

- A **Mac** with the FantaBuzzer kit plugged in, running the auction.

  > **Early days.** So far this has only been tested on one machine — a Mac with
  > Apple Silicon (M4). It should work on any modern macOS, but nobody has
  > checked yet. Windows isn't done at all; the keystroke layer is one small
  > file behind an interface, so it's a contained addition. A wider-tested
  > release is coming.
- **Python 3.14** and [uv](https://docs.astral.sh/uv/).
- Optional: `cloudflared`, only if someone is playing from outside the house.

## Setup

```bash
make install
```

Then grant Accessibility permission — without it macOS won't let the app type
anything at all:

**System Settings → Privacy & Security → Accessibility** → enable the terminal
you'll run this from, then restart it.

Grant it to the terminal you'll *actually* use: it's per-app and doesn't carry
over from one to another. The app refuses to start without it and says so,
rather than failing silently mid-auction.

## Running it

```bash
make run
```

```
╭─────────────────── astabuzz ───────────────────────╮
│ In casa (stesso wifi)   http://192.168.1.122:8787   │
│ Da fuori casa           https://xxx.trycloudflare.com│
│                                                     │
│ PIN  4271                                           │
╰───────────── Ctrl-C per fermare tutto ──────────────╯
```

Send whichever link fits — the local one for anyone on your wifi, the other for
whoever is playing from elsewhere. Every press appears live in your terminal,
with the app that received it:

```
18:22:04  P8 (H) -> FantaAstaBuzz
```

`Ctrl-C` stops everything. The public link dies with it.

| Command | |
| --- | --- |
| `make run` | Local + public link, live press log |
| `make run-local` | Local only, no public link |
| `make start` / `make stop` | The same, in the background |
| `make status` | Is it running? Link and PIN |
| `make logs` | Follow the background log |
| `make test` / `make check` | Tests, lint |

## Settings

Rather than passing flags every time, put what you want in a `.env`:

```bash
cp .env.example .env
```

```ini
ASTABUZZ_PIN=1998                        # fixed PIN, 4 digits. Omit for a new random one each run
ASTABUZZ_DOMAIN=astabuzz.example.com     # your own hostname. Omit for a throwaway link
ASTABUZZ_BUTTONS=12                      # 1 to 12. Default 8
ASTABUZZ_PORT=8787
```

Then plain `make run` uses all of it. A flag still wins for a one-off:

```bash
make run PIN=4242          # just this once
```

`.env` is gitignored, since your PIN lives in it. A bad value is caught at
startup with the name of the offending setting, not at the first login when
you've already read the PIN out to everyone.


## Try it without an auction

The vendor's own tester is the easiest proof:

1. `make run-local`
2. Open <https://www.fantabuzzer.com/kit-tester.html>, click *Avvia test*, and
   leave the tab in front.
3. From your phone on the same wifi, open the link, enter the PIN, press.
4. The tester lights up the button you pressed.

That page detects presses the same way FantaAsta Buzz does, so if it reacts, the
real thing will too.

## If the public link doesn't work

You'll see this in the terminal a few seconds after start:

```
! Il link pubblico non risponde (errore 530 di Cloudflare: il tunnel non si è registrato).
```

Free quick tunnels are best-effort, and occasionally one is handed a hostname
that Cloudflare never routes — every request then comes back as **530 (error
1033)**. Creating many in a short time makes it likelier. Stop and start again
to get a fresh one, and use the local link in the meantime.

The page tells the three failures apart, so nobody has to guess:

| On the phone | Means |
| --- | --- |
| `PIN errato` | The PIN really was wrong (server said 401) |
| `Nessuna connessione al server` | The request never arrived — wifi, tunnel or server down. Capped at 3 s, so it never just sits there |
| `Richiesta rifiutata (530)` | The tunnel is up but Cloudflare can't reach it |

Every refusal is also printed on the Mac, with the caller's address and the
reason:

```
11:30:10  rifiutata  192.168.1.122  PIN rifiutato: ricevuto '0000', atteso '4860'
```

## If a press doesn't register

The log tells you the letter was sent and where it landed. If it says
`-> FantaAstaBuzz` and nothing happens, the app is refusing it, and its own
handler gives the reasons:

- **Buzzer mode is off** — turn it on in `Opzioni`.
- **No round is running** — a bid with the countdown stopped is dropped.
- **Teams aren't mapped to buttons** — the letter resolves to nobody.
- **It's someone else's turn**, or you're already the highest bidder and
  self-raise is disabled.
- **Two offers landed within the concurrency window** and cancelled out.

## Is it safe?

The honest answer: the worst this can do is type one of eight letters, `a` to
`h`, into whatever window is in front. Not arbitrary text, not a command, not a
file. The button number is an index into a fixed eight-entry table and never
reaches the OS as text.

Beyond that: the public link is an outbound tunnel, so **no port is opened on
your router**, and it stops existing when you stop the server. The PIN is four
digits with no lockout — a deliberate choice for a three-hour evening with
friends, not a security posture. Anyone on your wifi who guesses it can buzz.
For a living room that's the right trade; if it isn't for you, run `make run-local`
and skip the public link entirely.

## Credits

All credit for the hardware, the idea and the auction software goes to the
**FantaBuzzer** and **Fantacalcio.it** teams. This project only presses their
buttons — it replaces nothing they made, and without their kit it does nothing
useful at all.

**Unofficial.** Not affiliated with, endorsed by, sponsored by or connected to
FantaBuzzer®, Fantacalcio® or Quadronica. Those names and logos are their
trademarks, referred to here only to identify the hardware this works with —
nominative use, no claim of ownership implied. If they'd rather I didn't, I'll
take them down.

**Experimental.** No warranty, no support, no guarantee it works on your setup.

## Versioning

[Commitizen](https://commitizen-tools.github.io/commitizen/) over conventional
commits, `uv` for the environment:

```bash
uv run cz commit   # guided conventional commit
uv run cz bump     # bump the version, tag, update the changelog
```

`cz bump` keeps `pyproject.toml`, `src/astabuzz/__init__.py` and the version
badge above in step.


## License

MIT — see [LICENSE](LICENSE).
