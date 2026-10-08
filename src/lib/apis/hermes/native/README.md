# Hermes native transport

These four TypeScript files are copied unchanged from `apps/shared/src` in
NousResearch/hermes-agent, as shipped in Hermes 0.21.5
(`f97608f178d1ffeca59860195ab7da295f7c8e5f`, release `v2026.9.24`).

The generated contract is the native gateway contract, not an OpenAI-compatible
chat contract. The request channel advertises server-request capability, returns
`-32601` for unsupported requests, and restores open requests after reconnect.
The gateway client handles heartbeat, sequence replay, epoch changes, and replay
barriers. No prompts, tools, model calls or credentials are implemented here.

When the Hermes runtime is upgraded, refresh these files together and verify the
transport and interaction tests before deploying the application.

Upstream: https://github.com/NousResearch/hermes-agent/tree/v2026.9.24/apps/shared/src

## License

MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
