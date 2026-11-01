# kindle

[![CI](https://github.com/spike442/containers/actions/workflows/ci.yml/badge.svg)](https://github.com/spike442/containers/actions/workflows/ci.yml)
[![Publish](https://github.com/spike442/containers/actions/workflows/publish.yml/badge.svg)](https://github.com/spike442/containers/actions/workflows/publish.yml)
[![Release](https://img.shields.io/github/v/tag/spike442/containers?label=release&sort=semver)](https://github.com/spike442/containers/tags)

Delivers reading material to a Kindle by email, without any manual step.
It runs next to the Bookshelf library and watches a Discord channel at the same time.
Every delivery, success or failure, is reported back on Discord.

**Library sync**

- Sends every new book that lands in the library, once, preferring EPUB over PDF.
- Waits for downloads to finish and retries failed deliveries until they go through.

**Article fetch**

- Turns any link posted in the channel into a clean, readable ebook with its images, and sends PDFs or EPUBs as they are.
- Sends whole online documentation books with a table of contents, reaching sites protected against bots when needed.
