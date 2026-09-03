from netconfig.db import Database
from netconfig.apitokens import ApiTokens

def test_api_token_is_hashed_scoped_and_revocable(tmp_path):
    db=Database(str(tmp_path/'x.db')); t=ApiTokens(db.conn)
    token_id, raw=t.create('grafana',['inventory:read','topology:read'],created_by='admin',role='viewer')
    assert raw.startswith('nct_')
    row=db.conn.execute('SELECT token_hash FROM api_tokens WHERE id=?',(token_id,)).fetchone()
    assert raw not in row['token_hash']
    v=t.verify(raw); assert v['role']=='viewer' and 'topology:read' in v['scopes']
    t.revoke(token_id); assert t.verify(raw) is None
    db.close()
