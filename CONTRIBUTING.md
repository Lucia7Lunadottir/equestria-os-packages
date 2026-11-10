# Contributing to Equestria OS

Thank you for wanting to help! Repo layout, tech stack and the most useful ways
to help are described in the [Contributing section of the README](README.md#-contributing).
This file covers the rules for sending changes.

## Before you start

* **Bugs:** open an Issue with your GPU model, laptop/desktop model, and
  Wayland or X11.
* **Anything non-trivial:** open an Issue first so we agree on the approach
  before you spend time on it.

## Sending changes

1. Fork the repository and create a branch for your change.
2. Keep each pull request about one thing.
3. Build and test the affected package with `makepkg -si` from its folder.
4. Sign off every commit (see below) and open a pull request.

## License of contributions

All code in this repository is licensed under the
[GNU GPL v3 or later](LICENSE). By contributing, you agree that your
contribution is licensed under the same terms.

## Developer Certificate of Origin

Every commit must be signed off — add `-s` to `git commit`:

```
git commit -s -m "Fix tray icon on X11"
```

This adds a `Signed-off-by: Your Name <you@example.com>` line, which certifies
that you wrote the change or otherwise have the right to submit it under the
project's license, as described in the
[Developer Certificate of Origin 1.1](https://developercertificate.org/).

## Names and branding

Please read [TRADEMARKS.md](TRADEMARKS.md) before redistributing a modified
version of Equestria OS.
