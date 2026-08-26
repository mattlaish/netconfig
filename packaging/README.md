# NetConfig RPM build (AlmaLinux 10)

This directory reconstructs the missing RPM source/build inputs. It builds an
unsigned test binary RPM and SRPM without using Git or including runtime data.


## Prepare the source on Windows

When the working copy is on Windows and the RPM will be built on AlmaLinux,
create a clean transfer bundle in the project root (not under `dist`):

```powershell
cd "C:\Users\mattlai\Projects\netconfig"
.\packaging\prepare-transfer.ps1
```

This produces `netconfig-2.0.0-16-rpm-build-source.zip`. Transfer that one ZIP
file to the AlmaLinux build host. The bundle contains only the application
payload, RPM tooling, and development/handover documents; it excludes Git data,
runtime state, Python caches, and previous RPM outputs.

## Build host preparation

Use an AlmaLinux 10 build host or disposable VM, not the production server:

```bash
sudo dnf install rpm-build python3.12
chmod +x packaging/*.sh
./packaging/build-rpm.sh
```

Artifacts are copied directly to the NetConfig project directory:

- `netconfig-2.0.0-16.el10.noarch.rpm`
- `netconfig-2.0.0-16.el10.src.rpm`

Inspect before installation:

```bash
./packaging/inspect-rpm.sh ./netconfig-2.0.0-16.el10.noarch.rpm
```

## Safe test sequence

1. Snapshot or clone an AlmaLinux 10.2 test VM.
2. Record `rpm -q netconfig` and back up `/var/lib/netconfig`.
3. Install the new RPM with `sudo dnf upgrade ./netconfig-2.0.0-16.el10.noarch.rpm`.
4. Run `./packaging/smoke-installed.sh`.
5. Start the service and verify the web, SNMP, MIB, backup timer, ownership,
   SELinux journal messages, and upgrade-retained vault/database content.
6. Do not deploy to production until a real-device SNMPv3 CPU/collection soak
   test passes.

The RPM intentionally leaves `/etc/default/netconfig` as `%config(noreplace)`
and owns only the `/var/lib/netconfig` directory, never its runtime contents.
The build also normalizes Linux launcher/unit text to LF; this prevents a
Windows-prepared source tree from producing systemd `203/EXEC` due to a CRLF
shebang.
