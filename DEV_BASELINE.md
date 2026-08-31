# NetConfig development baseline

- Source artifact: `netconfig-2.0.0-14.noarch.rpm`
- Artifact SHA-256: `076d2a3b5538061474235e9fe3b4313903561427d68c50af58310221bae391f1`
- RPM name/version/release: `netconfig-2.0.0-14`
- Payload entries: 41
- Installed payload size: 456829 bytes
- Application source: `opt/netconfig/`
- RPM integration files: `etc/`, `usr/`, and `var/`

This directory is a source reconstruction of the RPM payload. The RPM install
scripts were inspected but were not executed. Make application changes under
`opt/netconfig/`; keep packaging/service changes in their original payload paths.

The current host is Windows. Linux-specific runtime paths (`pty`, OpenSSH,
systemd, ownership and permission behavior) require verification in a Linux test
environment before producing the next RPM.
