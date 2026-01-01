import sqlite3
c=sqlite3.connect('autopack.db')
cur=c.cursor()
print('run:', cur.execute("SELECT id,state,updated_at FROM runs WHERE id='research-system-v29'").fetchone())
print('active tier phases:')
# show phases in earliest non-complete tier
active_tier = cur.execute("SELECT MIN(t.tier_index) FROM tiers t JOIN phases p ON p.tier_id=t.id WHERE p.run_id=? AND p.state!='COMPLETE'", ('research-system-v29',)).fetchone()[0]
print('active_tier_index=', active_tier)
rows = cur.execute("SELECT t.tier_id,t.tier_index,p.phase_id,p.state,p.retry_attempt,p.last_failure_reason,p.updated_at FROM phases p JOIN tiers t ON p.tier_id=t.id WHERE p.run_id=? AND t.tier_index=? ORDER BY p.phase_index", ('research-system-v29', active_tier)).fetchall()
for r in rows:
    print(r)
