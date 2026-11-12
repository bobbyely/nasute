# Security

Nasute runs on your own machine and sends questions to the systems and judge you name in its settings. The parts that matter most for security are how it handles keys (header values read from environment variables, never written to a run or a report) and the static report pages (text inserted as text, never as HTML).

## Reporting a problem

Please do not open a public issue for a security problem. Use GitHub's private reporting instead: on this repo's **Security** tab, choose **Report a vulnerability**. Say what you found, how to reproduce it, and which version you used (`pip show nasute`).

You should get a reply within two weeks. Once a fix is out, the changelog says what was fixed, and credits you if you want.

## Supported versions

Only the latest release gets fixes.
