import os, json, hmac, hashlib, sqlite3, secrets
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qsl
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB=os.getenv('DB_PATH','./ovo_gift.db')
BOT_TOKEN=os.getenv('BOT_TOKEN','')
BOT_USERNAME=os.getenv('BOT_USERNAME','Ovoz_giftbot')
OWNER_IDS={int(x) for x in os.getenv('OWNER_IDS','8884758319,7891819965').split(',') if x.strip().isdigit()}

app=FastAPI(title='OVOZ GIFT API',version='1.0.0')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])

def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
 c=db();
 c.executescript('''
 CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,telegram_id INTEGER UNIQUE,username TEXT,first_name TEXT,last_name TEXT,photo_url TEXT,stars INTEGER NOT NULL DEFAULT 0,referrer_id INTEGER,created_at TEXT,updated_at TEXT,banned_until TEXT);
 CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,type TEXT,amount INTEGER,status TEXT,meta TEXT,created_at TEXT);
 CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,title TEXT,description TEXT,link TEXT,reward INTEGER DEFAULT 1,active INTEGER DEFAULT 1,channel_username TEXT);
 CREATE TABLE IF NOT EXISTS task_claims(task_id TEXT,user_id INTEGER,status TEXT,created_at TEXT,PRIMARY KEY(task_id,user_id));
 CREATE TABLE IF NOT EXISTS referrals(id INTEGER PRIMARY KEY AUTOINCREMENT,referrer_id INTEGER,referred_id INTEGER,reward INTEGER,created_at TEXT,UNIQUE(referred_id));
 CREATE TABLE IF NOT EXISTS spins(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,reward INTEGER,created_at TEXT);
 CREATE TABLE IF NOT EXISTS withdrawals(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,amount INTEGER,status TEXT,created_at TEXT,updated_at TEXT);
 CREATE TABLE IF NOT EXISTS admins(telegram_id INTEGER PRIMARY KEY,role TEXT NOT NULL,permissions TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,admin_id INTEGER,action TEXT,target TEXT,meta TEXT,created_at TEXT);
 CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT);
 ''')
 c.execute("INSERT OR IGNORE INTO settings(k,v) VALUES('referral_reward','3')")
 c.execute("INSERT OR IGNORE INTO settings(k,v) VALUES('free_spin_hours','24')")
 c.execute("INSERT OR IGNORE INTO settings(k,v) VALUES('min_withdrawal','5')")
 c.execute("INSERT OR IGNORE INTO tasks(id,title,description,link,reward,channel_username) VALUES('channel','Kanalga qo\'shiling','Majburiy kanalga obuna bo\'ling','#',1,'')")
 for oid in OWNER_IDS: c.execute("INSERT OR IGNORE INTO admins(telegram_id,role,permissions) VALUES(?,?,?)",(oid,'Owner','[\"*\"]'))
 c.commit(); c.close()
init_db()

def now(): return datetime.now(timezone.utc)
def iso(dt): return dt.isoformat()

def telegram_user(init_data):
 if not init_data:
  # local/browser demo account
  return {'id':0,'first_name':'Demo User','username':'demo'}
 pairs=dict(parse_qsl(init_data,keep_blank_values=True)); raw_hash=pairs.pop('hash',None)
 if not raw_hash: raise HTTPException(401,'Invalid Telegram initData')
 if not BOT_TOKEN: raise HTTPException(500,'BOT_TOKEN is not configured')
 check='\n'.join(f'{k}={pairs[k]}' for k in sorted(pairs))
 secret=hmac.new(b'WebAppData',BOT_TOKEN.encode(),hashlib.sha256).digest()
 calc=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
 if not hmac.compare_digest(calc,raw_hash): raise HTTPException(401,'Invalid Telegram signature')
 import json as _json
 u=_json.loads(pairs.get('user','{}')); return u

def current_user(init_data):
 u=telegram_user(init_data); tid=int(u.get('id',0))
 c=db(); row=c.execute('SELECT * FROM users WHERE telegram_id=?',(tid,)).fetchone()
 if not row:
  c.execute('INSERT INTO users(telegram_id,username,first_name,last_name,photo_url,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(tid,u.get('username'),u.get('first_name',''),u.get('last_name',''),u.get('photo_url'),iso(now()),iso(now()))); c.commit(); row=c.execute('SELECT * FROM users WHERE telegram_id=?',(tid,)).fetchone()
 c.close(); return row

def admin_for(tid):
 c=db(); r=c.execute('SELECT * FROM admins WHERE telegram_id=?',(tid,)).fetchone(); c.close(); return r

def tx(c,uid,typ,amount,status='completed',meta=None): c.execute('INSERT INTO transactions(user_id,type,amount,status,meta,created_at) VALUES(?,?,?,?,?,?)',(uid,typ,amount,status,json.dumps(meta or {}),iso(now())))

def audit(admin,action,target='',meta=None):
 c=db(); c.execute('INSERT INTO audit_logs(admin_id,action,target,meta,created_at) VALUES(?,?,?,?,?)',(admin,action,target,json.dumps(meta or {}),iso(now()))); c.commit(); c.close()

class Amount(BaseModel): amount:int
class AdminBody(BaseModel): telegram_id:int; role:str='Admin'; permissions:list[str]=[]
class BalanceBody(BaseModel): amount:int; reason:str='admin adjustment'
class BanBody(BaseModel): hours:int=0

@app.get('/api/health')
def health(): return {'ok':True,'name':'OVOZ GIFT','version':'1.0.0'}

@app.get('/api/me')
def me(x_telegram_init_data: str|None=Header(default=None)):
 u=current_user(x_telegram_init_data); tid=u['telegram_id']; c=db();
 last=c.execute('SELECT created_at FROM spins WHERE user_id=? ORDER BY id DESC LIMIT 1',(u['id'],)).fetchone();
 available=True
 if last:
  available=(now()-datetime.fromisoformat(last['created_at'])).total_seconds()>=24*3600
 refs=c.execute('SELECT COUNT(*) n FROM referrals WHERE referrer_id=?',(u['id'],)).fetchone()['n']; rank=c.execute('SELECT COUNT(*) n FROM users WHERE stars>?',(u['stars'],)).fetchone()['n']+1
 a=admin_for(tid); c.close()
 return {'user':dict(u),'stars':u['stars'],'freeSpinAvailable':available,'referrals':refs,'rank':rank,'admin':dict(a) if a else None,'botUsername':BOT_USERNAME}

@app.post('/api/spin/free')
def free_spin(x_telegram_init_data: str|None=Header(default=None)):
 u=current_user(x_telegram_init_data); c=db(); last=c.execute('SELECT created_at FROM spins WHERE user_id=? ORDER BY id DESC LIMIT 1',(u['id'],)).fetchone()
 if last and (now()-datetime.fromisoformat(last['created_at'])).total_seconds()<24*3600: c.close(); raise HTTPException(400,'Free spin is available once every 24 hours')
 # Safe promotional reward: no paid wagering and no real-world prize odds.
 reward=secrets.choice([1,1,1,2,2,3]); c.execute('INSERT INTO spins(user_id,reward,created_at) VALUES(?,?,?)',(u['id'],reward,iso(now()))); c.execute('UPDATE users SET stars=stars+?,updated_at=? WHERE id=?',(reward,iso(now()),u['id'])); tx(c,u['id'],'free_spin',reward); c.commit(); c.close(); return {'ok':True,'reward':reward}

@app.get('/api/tasks')
def tasks(x_telegram_init_data: str|None=Header(default=None)):
 u=current_user(x_telegram_init_data); c=db(); rows=c.execute('SELECT t.*,tc.status FROM tasks t LEFT JOIN task_claims tc ON tc.task_id=t.id AND tc.user_id=? WHERE t.active=1',(u['id'],)).fetchall(); c.close(); return {'tasks':[dict(r) for r in rows]}

@app.post('/api/tasks/{task_id}/claim')
def claim(task_id:str,x_telegram_init_data: str|None=Header(default=None)):
 u=current_user(x_telegram_init_data); c=db(); t=c.execute('SELECT * FROM tasks WHERE id=? AND active=1',(task_id,)).fetchone()
 if not t: c.close(); raise HTTPException(404,'Task not found')
 old=c.execute('SELECT * FROM task_claims WHERE task_id=? AND user_id=?',(task_id,u['id'])).fetchone()
 if old and old['status']=='completed': c.close(); return {'ok':False,'message':'Already claimed'}
 # Channel verification can be added when channel_username and BOT_TOKEN are configured.
 c.execute('INSERT OR REPLACE INTO task_claims(task_id,user_id,status,created_at) VALUES(?,?,?,?)',(task_id,u['id'],'completed',iso(now())))
 c.execute('UPDATE users SET stars=stars+?,updated_at=? WHERE id=?',(t['reward'],iso(now()),u['id'])); tx(c,u['id'],'task_bonus',t['reward'],meta={'task_id':task_id}); c.commit(); c.close(); return {'ok':True,'reward':t['reward']}

@app.get('/api/referral')
def referral(x_telegram_init_data: str|None=Header(default=None)):
 u=current_user(x_telegram_init_data); c=db(); reward=int(c.execute("SELECT v FROM settings WHERE k='referral_reward'").fetchone()['v']); n=c.execute('SELECT COUNT(*) n FROM referrals WHERE referrer_id=?',(u['id'],)).fetchone()['n']; c.close(); return {'link':f'https://t.me/{BOT_USERNAME}?startapp=ref_{u["telegram_id"]}','reward':reward,'count':n}

@app.get('/api/ranking')
def ranking():
 c=db(); rows=c.execute('SELECT first_name,username,stars FROM users WHERE banned_until IS NULL ORDER BY stars DESC LIMIT 20').fetchall(); c.close(); return {'items':[dict(r) for r in rows]}

@app.get('/api/history')
def history(x_telegram_init_data: str|None=Header(default=None)):
 u=current_user(x_telegram_init_data); c=db(); rows=c.execute('SELECT type,amount,status,created_at,meta FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 100',(u['id'],)).fetchall(); c.close(); return {'items':[dict(r) for r in rows]}

@app.post('/api/withdraw')
def withdraw(body:Amount,x_telegram_init_data: str|None=Header(default=None)):
 u=current_user(x_telegram_init_data); c=db(); minw=int(c.execute("SELECT v FROM settings WHERE k='min_withdrawal'").fetchone()['v']);
 if body.amount<minw: c.close(); raise HTTPException(400,f'Minimum withdrawal is {minw} Stars')
 if body.amount>u['stars']: c.close(); raise HTTPException(400,'Insufficient balance')
 c.execute('UPDATE users SET stars=stars-? WHERE id=?',(body.amount,u['id'])); c.execute('INSERT INTO withdrawals(user_id,amount,status,created_at,updated_at) VALUES(?,?,?,?,?)',(u['id'],body.amount,'pending',iso(now()),iso(now()))); tx(c,u['id'],'withdrawal',-body.amount,'pending'); c.commit(); wid=c.execute('SELECT last_insert_rowid() x').fetchone()['x']; c.close(); return {'ok':True,'id':wid,'status':'pending'}

@app.get('/api/admin/summary')
def admin_summary(x_telegram_init_data: str|None=Header(default=None)):
 u=current_user(x_telegram_init_data); a=admin_for(u['telegram_id']);
 if not a: raise HTTPException(403,'Admin only')
 c=db(); d={'users':c.execute('SELECT COUNT(*) n FROM users').fetchone()['n'],'balance':c.execute('SELECT COALESCE(SUM(stars),0) n FROM users').fetchone()['n'],'spins':c.execute('SELECT COUNT(*) n FROM spins').fetchone()['n'],'referrals':c.execute('SELECT COUNT(*) n FROM referrals').fetchone()['n'],'pendingWithdrawals':c.execute("SELECT COUNT(*) n FROM withdrawals WHERE status='pending'").fetchone()['n'],'withdrawals':c.execute('SELECT COALESCE(SUM(amount),0) n FROM withdrawals WHERE status=\'pending\'').fetchone()['n']}; c.close(); return d

@app.get('/api/admin/users')
def admin_users(x_telegram_init_data: str|None=Header(default=None)):
 u=current_user(x_telegram_init_data); 
 if not admin_for(u['telegram_id']): raise HTTPException(403,'Admin only')
 c=db(); rows=c.execute('SELECT * FROM users ORDER BY id DESC LIMIT 500').fetchall(); c.close(); return {'items':[dict(r) for r in rows]}

@app.post('/api/admin/users/{telegram_id}/balance')
def admin_balance(telegram_id:int,body:BalanceBody,x_telegram_init_data: str|None=Header(default=None)):
 u=current_user(x_telegram_init_data); a=admin_for(u['telegram_id']);
 if not a: raise HTTPException(403,'Admin only')
 c=db(); r=c.execute('SELECT * FROM users WHERE telegram_id=?',(telegram_id,)).fetchone();
 if not r: c.close(); raise HTTPException(404,'User not found')
 if r['stars']+body.amount<0: c.close(); raise HTTPException(400,'Balance cannot be negative')
 c.execute('UPDATE users SET stars=stars+?,updated_at=? WHERE telegram_id=?',(body.amount,iso(now()),telegram_id)); tx(c,r['id'],'admin_adjustment',body.amount,meta={'reason':body.reason,'admin':u['telegram_id']}); c.commit(); c.close(); audit(u['telegram_id'],'balance_change',str(telegram_id),{'amount':body.amount,'reason':body.reason}); return {'ok':True}

@app.get('/api/admin/withdrawals')
def admin_withdrawals(x_telegram_init_data: str|None=Header(default=None)):
 u=current_user(x_telegram_init_data); 
 if not admin_for(u['telegram_id']): raise HTTPException(403,'Admin only')
 c=db(); rows=c.execute('SELECT w.*,u.telegram_id,u.username,u.first_name FROM withdrawals w JOIN users u ON u.id=w.user_id ORDER BY w.id DESC LIMIT 500').fetchall(); c.close(); return {'items':[dict(r) for r in rows]}

@app.post('/api/admin/withdrawals/{wid}/{action}')
def admin_withdrawal(wid:int,action:str,x_telegram_init_data: str|None=Header(default=None)):
 u=current_user(x_telegram_init_data); 
 if not admin_for(u['telegram_id']): raise HTTPException(403,'Admin only')
 if action not in {'approve','reject'}: raise HTTPException(400,'Invalid action')
 c=db(); w=c.execute('SELECT * FROM withdrawals WHERE id=?',(wid,)).fetchone();
 if not w or w['status']!='pending': c.close(); raise HTTPException(400,'Request unavailable')
 status='approved' if action=='approve' else 'rejected'
 if status=='rejected': c.execute('UPDATE users SET stars=stars+? WHERE id=?',(w['amount'],w['user_id'])); tx(c,w['user_id'],'withdrawal_refund',w['amount'])
 c.execute('UPDATE withdrawals SET status=?,updated_at=? WHERE id=?',(status,iso(now()),wid)); c.commit(); c.close(); audit(u['telegram_id'],action,str(wid)); return {'ok':True,'status':status}

@app.post('/api/admin/admins')
def add_admin(body:AdminBody,x_telegram_init_data: str|None=Header(default=None)):
 u=current_user(x_telegram_init_data); 
 if u['telegram_id'] not in OWNER_IDS: raise HTTPException(403,'Owner only')
 c=db(); c.execute('INSERT OR REPLACE INTO admins(telegram_id,role,permissions) VALUES(?,?,?)',(body.telegram_id,body.role,json.dumps(body.permissions))); c.commit(); c.close(); audit(u['telegram_id'],'add_admin',str(body.telegram_id),body.model_dump()); return {'ok':True}

@app.delete('/api/admin/admins/{telegram_id}')
def remove_admin(telegram_id:int,x_telegram_init_data: str|None=Header(default=None)):
 u=current_user(x_telegram_init_data); 
 if u['telegram_id'] not in OWNER_IDS: raise HTTPException(403,'Owner only')
 if telegram_id in OWNER_IDS: raise HTTPException(400,'Owner cannot be removed')
 c=db(); c.execute('DELETE FROM admins WHERE telegram_id=?',(telegram_id,)); c.commit(); c.close(); audit(u['telegram_id'],'remove_admin',str(telegram_id)); return {'ok':True}

@app.get('/api/admin/logs')
def logs(x_telegram_init_data: str|None=Header(default=None)):
 u=current_user(x_telegram_init_data); 
 if not admin_for(u['telegram_id']): raise HTTPException(403,'Admin only')
 c=db(); rows=c.execute('SELECT * FROM audit_logs ORDER BY id DESC LIMIT 300').fetchall(); c.close(); return {'items':[dict(r) for r in rows]}
