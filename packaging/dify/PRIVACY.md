# Privacy Policy — Web Novel Writing Validator (Dify Plugin)

**Last updated: 2026-10-16**

## What this plugin processes

This plugin runs local, text-only validation scripts on **the chapter text you pass
into a tool parameter**. The text is written to a temporary file inside the plugin
sandbox solely so the validator script can read it, and that temporary file is
deleted immediately after the script returns.

## What is collected or transmitted

- **Nothing is sent to the plugin author.** The plugin author operates no server
  and receives no data from this plugin.
- The plugin makes **no outbound network requests**.
- The plugin does **not** read files outside the sandbox, and does **not** access
  any local user directory. All tools accept text, not file paths.
- No telemetry, no analytics, no cookies, no user identifiers.

## Third parties

None. The plugin has a single dependency, `dify_plugin` (the Dify plugin SDK),
which provides the runtime only.

## Data retention

No data is retained by this plugin. Temporary files live only for the duration of
a single tool invocation.

## Your responsibility

The chapter text you submit passes through **your own Dify deployment**. How your
Dify workspace stores conversation and tool inputs is governed by Dify's privacy
policy and your own deployment configuration, not by this plugin.

## Contact

Issues and questions: <https://github.com/lenmo181/novel-writing-skill/issues>
