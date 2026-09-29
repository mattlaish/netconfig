import html

from . import config as _config


class WebDatabaseMixin:
    """R67.2 Core/History PostgreSQL settings and fail-closed preflight."""

    def _database_settings_content(self, s, form):
        from . import ifhistory as _ifh
        from .credentials import postgres_core_password
        history_pw_set = False
        if self.manager.vault_ready():
            try:
                history_pw_set = bool(self.manager.vault.get_secret(
                    _ifh.VAULT_SECRET).get("password"))
            except Exception:
                pass
        try:
            _core_secret, core_secret_source = postgres_core_password()
        except Exception:
            core_secret_source = None
        core_secret_label = (
            f"configured via {html.escape(core_secret_source)}" if core_secret_source
            else "NOT configured"
        )
        modes = ("disable", "allow", "prefer", "require", "verify-ca", "verify-full")
        core_sslmodes = "".join(
            f'<option value="{v}"{" selected" if s.get("pg_sslmode")==v else ""}>{v}</option>'
            for v in modes)

        history_dedicated = bool((s.get("if_history_pg_host") or "").strip() or
                                 (s.get("if_history_pg_dbname") or "").strip())
        def hv(name, legacy):
            return s.get(name) if history_dedicated else s.get(legacy)
        def field(key, label, hint=""):
            return (f'<div><label>{html.escape(label)}</label>'
                    f'<input name="{key}" value="{html.escape(str(s.get(key, "")))}">'
                    f'{f"<div class=muted>{hint}</div>" if hint else ""}</div>')
        def hfield(key, legacy, label, hint=""):
            value = hv(key, legacy)
            return (f'<div><label>{html.escape(label)}</label>'
                    f'<input name="{key}" value="{html.escape(str(value or ""))}">'
                    f'{f"<div class=muted>{hint}</div>" if hint else ""}</div>')
        hist_ssl = hv("if_history_pg_sslmode", "pg_sslmode") or "prefer"
        history_sslmodes = "".join(
            f'<option value="{v}"{" selected" if hist_ssl==v else ""}>{v}</option>'
            for v in modes)
        core_form = form + '<input type=hidden name=db_scope value="core">'
        history_form = form + '<input type=hidden name=db_scope value="history">'
        return f"""<div class="panel"><h2>Core Database</h2>
<p class="muted">The control-plane database is separate from Interface History. PostgreSQL
selection is fail-closed: Save is refused unless the psycopg 3 driver, host/database, protected
pre-vault credential, connection, and schema bootstrap all pass. A successful change takes effect
after process restart. Core credential status: <b>{core_secret_label}</b>.</p>
{core_form}<div class="row"><div><label>Core database backend</label>
<select name=core_db_backend><option value="sqlite"{" selected" if s.get("core_db_backend","sqlite")=="sqlite" else ""}>SQLite — single node</option><option value="postgres"{" selected" if s.get("core_db_backend")=="postgres" else ""}>PostgreSQL — distributed capable</option></select>
<div class=muted>Backend changes require a process restart.</div></div>
{field("core_db_application_name","PostgreSQL application name","netconfig")}</div>
<div class="row">{field("pg_host","Core PostgreSQL host","hostname or IP")}
{field("pg_port","Core PostgreSQL port","default 5432")}{field("pg_dbname","Core database name")}</div>
<div class="row">{field("pg_user","Core database username")}
<div><label>Core SSL mode</label><select name=pg_sslmode>{core_sslmodes}</select></div></div>
<div class="row">{field("cluster_node_id","Cluster node ID","blank = hostname:pid")}
{field("cluster_failure_domain","Failure domain","rack/AZ/site; required for multi-node HA readiness")}</div>
<div class="row">{field("cluster_stale_seconds","Node stale threshold (s)","default 90")}
{field("distributed_task_lease_seconds","Task lease (s)","default 60")}</div>
<button>Save Core Database settings</button>
<button formaction="/core-db-test" formmethod="post" class=ghost style="margin-left:8px">Test &amp; bootstrap Core PostgreSQL</button></form></div>

<div class="panel"><h2>Interface History Store</h2>
<p class="muted">Optional long-term interface-rate history. This connection is independent from
the Core Database. Existing installations temporarily inherit legacy shared PostgreSQL fields until
these History settings are saved.</p>
{history_form}<div class="row"><div><label>Interface history store</label>
<label style="color:var(--text);font-weight:400"><input type=checkbox name=if_history_enabled value=1 style="width:auto" {"checked" if s.get("if_history_enabled") else ""}> enabled</label></div>
{hfield("if_history_pg_host","pg_host","History PostgreSQL host","hostname or IP")}
{hfield("if_history_pg_port","pg_port","History PostgreSQL port","default 5432")}</div>
<div class="row">{hfield("if_history_pg_dbname","pg_dbname","History database name")}
{hfield("if_history_pg_user","pg_user","History database username")}
<div><label>History SSL mode</label><select name=if_history_pg_sslmode>{history_sslmodes}</select></div></div>
<div class="row"><div><label>Interface-history password{" ✓ set" if history_pw_set else ""}</label>
<input type=password name=if_history_pg_password placeholder="history store only; kept in vault"></div>
{field("if_history_hours","History retention (hours)","default graph window; e.g. 24")}
{field("if_history_bucket_seconds","Downsample bucket (s)","points averaged into this bucket")}</div>
<button>Save Interface History settings</button>
<button formaction="/history-db-test" formmethod="post" class=ghost style="margin-left:8px">Test History PostgreSQL</button></form></div>"""

    def _save_database_settings(self, form, sess, g):
        s = self.manager.settings
        scope = g("db_scope") or "core"
        if scope == "core":
            candidate = dict(s)
            for key in ("core_db_backend", "core_db_application_name", "cluster_node_id",
                        "cluster_failure_domain", "pg_host", "pg_dbname", "pg_user", "pg_sslmode"):
                candidate[key] = g(key)
            for key in ("pg_port", "cluster_stale_seconds", "distributed_task_lease_seconds"):
                if g(key):
                    try:
                        candidate[key] = int(g(key))
                    except ValueError:
                        return self._settings_page_v2(
                            sess, q={"section": ["db"]}, flash=f"Invalid integer value for {key}.")
            backend = (candidate.get("core_db_backend") or "sqlite").lower()
            if backend not in {"sqlite", "postgres"}:
                return self._settings_page_v2(sess, q={"section": ["db"]},
                                              flash="Invalid Core Database backend.")
            if backend == "postgres":
                from .credentials import postgres_core_password
                from .postgres_core import preflight_core_postgres
                try:
                    password, _source = postgres_core_password()
                except Exception as exc:
                    return self._settings_page_v2(
                        sess, q={"section": ["db"]},
                        flash="Core PostgreSQL preflight failed at credential: " + str(exc)[:240])
                result = preflight_core_postgres(candidate, password=password)
                if not result.get("ok"):
                    return self._settings_page_v2(
                        sess, q={"section": ["db"]},
                        flash=("Core PostgreSQL settings NOT saved — preflight failed at "
                               f"{result.get('stage','unknown')}: {result.get('error','unknown error')}"))
            for key in ("core_db_backend", "core_db_application_name", "cluster_node_id",
                        "cluster_failure_domain", "pg_host", "pg_port", "pg_dbname", "pg_user",
                        "pg_sslmode", "cluster_stale_seconds", "distributed_task_lease_seconds"):
                if key in candidate:
                    s[key] = candidate[key]
            _config.save_settings(self.manager.paths, s)
            self.manager.db.audit(sess["username"], "settings_save", "db-core", backend)
            suffix = " Restart NetConfig to activate the backend change."
            if backend == "postgres":
                suffix = " Core PostgreSQL preflight/bootstrap passed." + suffix
            return self._settings_page_v2(sess, q={"section": ["db"]},
                                          flash="Core Database settings saved." + suffix)

        if scope == "history":
            from . import ifhistory as _ifh
            candidate = dict(s)
            candidate["if_history_enabled"] = bool(form.get("if_history_enabled"))
            for key in ("if_history_pg_host", "if_history_pg_dbname", "if_history_pg_user",
                        "if_history_pg_sslmode"):
                candidate[key] = g(key)
            for key in ("if_history_pg_port", "if_history_hours", "if_history_bucket_seconds"):
                if g(key):
                    try:
                        candidate[key] = int(g(key))
                    except ValueError:
                        return self._settings_page_v2(
                            sess, q={"section": ["db"]}, flash=f"Invalid integer value for {key}.")
            pw = (form.get("if_history_pg_password") or [""])[0]
            if pw:
                try:
                    if self.manager.vault_ready():
                        self.manager.vault.set_secret(_ifh.VAULT_SECRET, password=pw)
                    else:
                        return self._settings_page_v2(
                            sess, q={"section": ["db"]},
                            flash="Unlock the vault before saving a History password.")
                except Exception as exc:
                    return self._settings_page_v2(
                        sess, q={"section": ["db"]}, flash="History password save failed: " + str(exc)[:240])
            s.update({k: candidate[k] for k in (
                "if_history_enabled", "if_history_pg_host", "if_history_pg_port",
                "if_history_pg_dbname", "if_history_pg_user", "if_history_pg_sslmode",
                "if_history_hours", "if_history_bucket_seconds") if k in candidate})
            _config.save_settings(self.manager.paths, s)
            self.manager._ifhist_key = None
            self.manager.db.audit(sess["username"], "settings_save", "db-history", "")
            flash = "Interface History settings saved."
            if s.get("if_history_enabled"):
                backend = self.manager._history_backend()
                if backend is None:
                    flash += " History is enabled but host/database is incomplete."
                else:
                    res = backend.ensure_ready()
                    flash += (" History PostgreSQL ready." if res["ok"]
                              else " History connection failed: " + (res["error"] or "unknown error"))
            return self._settings_page_v2(sess, q={"section": ["db"]}, flash=flash)

        return self._settings_page_v2(sess, q={"section": ["db"]}, flash="Invalid Database settings scope.")

    def _do_core_db_test(self, form, sess):
        if not self._database_settings_allowed(sess):
            return self._settings_page_v2(sess, q={"section": ["db"]}, flash="Not permitted.")
        from .credentials import postgres_core_password
        from .postgres_core import preflight_core_postgres
        def g(k):
            return (form.get(k) or [""])[0].strip()
        candidate = dict(self.manager.settings)
        for key in ("core_db_application_name", "pg_host", "pg_dbname", "pg_user", "pg_sslmode"):
            if g(key):
                candidate[key] = g(key)
        if g("pg_port"):
            try:
                candidate["pg_port"] = int(g("pg_port"))
            except ValueError:
                return self._settings_page_v2(sess, q={"section": ["db"]}, flash="Invalid Core PostgreSQL port.")
        try:
            password, _source = postgres_core_password()
        except Exception as exc:
            return self._settings_page_v2(sess, q={"section": ["db"]},
                                          flash="Core PostgreSQL credential failed: " + str(exc)[:240])
        result = preflight_core_postgres(candidate, password=password)
        if result.get("ok"):
            msg = "Core PostgreSQL connection/schema bootstrap OK — settings were not changed."
        else:
            msg = ("Core PostgreSQL test failed at " + str(result.get("stage", "unknown")) +
                   ": " + str(result.get("error", "unknown error")))
        return self._settings_page_v2(sess, q={"section": ["db"]}, flash=msg)

    def _do_history_db_test(self, form, sess):
        if not self._database_settings_allowed(sess):
            return self._settings_page_v2(sess, q={"section": ["db"]}, flash="Not permitted.")
        from . import ifhistory as _ifh
        def g(k):
            return (form.get(k) or [""])[0].strip()
        candidate = dict(self.manager.settings)
        for key in ("if_history_pg_host", "if_history_pg_dbname", "if_history_pg_user",
                    "if_history_pg_sslmode"):
            if g(key):
                candidate[key] = g(key)
        if g("if_history_pg_port"):
            try:
                candidate["if_history_pg_port"] = int(g("if_history_pg_port"))
            except ValueError:
                return self._settings_page_v2(sess, q={"section": ["db"]}, flash="Invalid History PostgreSQL port.")
        pw = (form.get("if_history_pg_password") or [""])[0] or self.manager._pg_password()
        backend = _ifh.build_backend(candidate, password=pw)
        if backend is None:
            return self._settings_page_v2(
                sess, q={"section": ["db"]}, flash="Set History PostgreSQL host and database first.")
        res = backend.ensure_ready()
        if res["ok"]:
            msg = ("History PostgreSQL OK — history table created." if res["created"]
                   else "History PostgreSQL OK — history table already present.")
        else:
            msg = "History PostgreSQL failed: " + (res["error"] or "unknown error")
        return self._settings_page_v2(sess, q={"section": ["db"]}, flash=msg)

    def _database_settings_allowed(self, sess):
        from .users import can
        return can(sess["role"], "settings")
