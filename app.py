import os, json, time, re
from datetime import datetime, timezone
from urllib.parse import quote
import requests
import streamlit as st

st.set_page_config(page_title='RAN-NEETI | Multiverse Analysis', page_icon='⚔️', layout='wide')

# ----------------------------- Configuration -----------------------------
SPORTS = {
    'Team sports': ['Football / Soccer', 'Cricket (Test)', 'Cricket (ODI)', 'Cricket (T20)', 'Basketball', 'Baseball', 'American Football', 'Rugby Union', 'Rugby League', 'Rugby Sevens', 'Ice Hockey', 'Field Hockey', 'Volleyball', 'Beach Volleyball', 'Handball', 'Kabaddi', 'Water Polo', 'Lacrosse', 'Futsal', 'Netball', 'Australian Rules Football'],
    'Racket & individual': ['Tennis', 'Badminton', 'Table Tennis', 'Squash', 'Pickleball', 'Golf', 'Boxing', 'MMA', 'Wrestling', 'Judo', 'Taekwondo', 'Karate', 'Fencing', 'Chess', 'Go', 'Esports'],
    'Racing & athletics': ['Formula 1 / Motorsport', 'MotoGP', 'Cycling', 'Athletics / Track & Field', 'Marathon', 'Swimming', 'Diving', 'Gymnastics', 'Weightlifting', 'Rowing', 'Canoe / Kayak', 'Skiing', 'Snowboarding', 'Skating', 'Surfing', 'Archery', 'Shooting', 'Triathlon'],
    'Other': ['Darts', 'Snooker / Pool', 'Billiards', 'Equestrian', 'Sailing', 'Sport Climbing', 'Figure Skating']
}
ALL_SPORTS = [v for group in SPORTS.values() for v in group]
FICTION_TYPES = ['Anime / Manga Fight', 'Anime Sports', 'Video-game Fighters', 'Comics / Fictional Characters', 'General Fictional Matchup']

st.markdown('''<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700;800&family=Inter:wght@400;500;600;700&display=swap');
.stApp{background:radial-gradient(ellipse at 12% 0%,#182747 0%,#080b14 52%,#090a12 100%);color:#edf3ff}
.block-container{max-width:1450px;padding-top:1.2rem;padding-bottom:3rem}
[data-testid="stSidebar"]{background:#0c1120;border-right:1px solid #293650}
h1,h2,h3{font-family:Orbitron,sans-serif!important}
.hero{padding:25px 30px;border:1px solid #293b5b;border-radius:20px;background:linear-gradient(115deg,rgba(22,35,63,.96),rgba(15,18,35,.92));margin-bottom:20px}
.brand{font:800 clamp(30px,4vw,52px) Orbitron,sans-serif;background:linear-gradient(90deg,#fff,#54e8ff 55%,#b69aff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;line-height:1.2}
.kicker{font:600 11px Orbitron,sans-serif;letter-spacing:3px;color:#54e8ff;text-transform:uppercase}
.panel{background:rgba(16,22,38,.82);border:1px solid #25314a;border-radius:16px;padding:16px 20px;margin-bottom:12px}
.small{color:#9ba8c2;font-size:12px}
.stButton>button{border:1px solid #54e8ff;background:linear-gradient(90deg,#173a50,#24234a);color:#f6fbff;border-radius:10px;font-family:Orbitron,sans-serif;font-weight:600;min-height:42px}
[data-testid="stMetric"]{background:#111a2b;border:1px solid #293b5b;padding:12px;border-radius:12px}
</style>''', unsafe_allow_html=True)

# ----------------------------- API helpers -----------------------------
def get_secret(name, default=''):
    value = os.getenv(name, '')
    try:
        if not value:
            value = st.secrets.get(name, '')
    except Exception:
        pass
    return str(value or default).strip()

def gemini_model():
    # Override in Streamlit secrets if Google changes model availability.
    return get_secret('GEMINI_MODEL', 'gemini-3.8-flash')

def request_json(method, url, **kwargs):
    """Small bounded retry for transient public-API failures; never retries auth/quota errors."""
    kwargs.setdefault('timeout', (10, 35))
    last = None
    for attempt in range(3):
        try:
            response = requests.request(method, url, **kwargs)
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                wait = min(2 ** attempt, 4)
                time.sleep(wait)
                last = response
                continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last = exc
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    if isinstance(last, requests.Response):
        last.raise_for_status()
    raise RuntimeError('Public data service did not respond.')

def mediawiki_lookup(query, limit=5):
    if not query.strip(): return []
    url = 'https://en.wikipedia.org/w/api.php'
    params = {'action':'query','format':'json','generator':'search','gsrsearch':query,'gsrlimit':limit,'prop':'pageimages|extracts|info','piprop':'thumbnail','pithumbsize':420,'exintro':1,'explaintext':1,'inprop':'url'}
    data = request_json('GET', url, params=params, headers={'User-Agent':'RAN-NEETI-MScDS-Project/1.0 (educational research app)'})
    pages = (data.get('query') or {}).get('pages') or {}
    rows=[]
    for p in sorted(pages.values(), key=lambda x:x.get('index',999)):
        rows.append({'title':p.get('title','Untitled'),'url':p.get('fullurl',''),'extract':p.get('extract',''),'image':(p.get('thumbnail') or {}).get('source',''),'source':'MediaWiki'})
    return rows

def jikan_lookup(query, limit=5):
    if not query.strip(): return []
    data = request_json('GET', 'https://api.jikan.moe/v4/characters', params={'q':query,'limit':limit}, headers={'User-Agent':'RAN-NEETI-MScDS-Project/1.0'})
    rows=[]
    for p in (data.get('data') or []):
        rows.append({'title':p.get('name','Unknown'),'url':p.get('url',''),'extract':p.get('about',''),'image':((p.get('images') or {}).get('jpg') or {}).get('image_url',''),'source':'Jikan'})
    return rows

def sportsdb_lookup(query, limit=5):
    """Free TheSportsDB entity search. It supplies team/player metadata, not guaranteed live scores."""
    if not query.strip():
        return []
    api_key = get_secret('SPORTSDB_API_KEY', '3')
    headers = {'User-Agent': 'RAN-NEETI-MScDS-Project/1.0'}
    records = []
    for endpoint, params, kind in [
        ('searchteams.php', {'t': query}, 'Team'),
        ('searchplayers.php', {'p': query}, 'Player'),
    ]:
        try:
            data = request_json('GET', f'https://www.thesportsdb.com/api/v1/json/{api_key}/{endpoint}', params=params, headers=headers)
            key = 'teams' if kind == 'Team' else 'player'
            for item in (data.get(key) or [])[:limit]:
                name = item.get('strTeam') or item.get('strPlayer') or query
                ident = item.get('idTeam') or item.get('idPlayer')
                records.append({
                    'title': name,
                    'url': f'https://www.thesportsdb.com/{"team" if kind == "Team" else "player"}/{ident}' if ident else 'https://www.thesportsdb.com/',
                    'extract': ' | '.join(x for x in [kind, item.get('strSport'), item.get('strLeague'), item.get('strCountry'), item.get('strPosition')] if x),
                    'image': item.get('strBadge') or item.get('strThumb') or '',
                    'source': 'TheSportsDB'
                })
        except Exception:
            # The app still works if this optional public data source is down.
            continue
    return records

def lookup_candidates(query, fictional=False):
    errors=[]
    if not fictional:
        try:
            found=sportsdb_lookup(query)
            if found: return found
        except Exception as e: errors.append('TheSportsDB: '+str(e))
    if fictional:
        try:
            found=jikan_lookup(query)
            if found: return found
        except Exception as e: errors.append('Jikan: '+str(e))
    try:
        found=mediawiki_lookup(query)
        if found: return found
    except Exception as e: errors.append('MediaWiki: '+str(e))
    return {'error':'; '.join(errors) if errors else 'No matching records were returned.'}

def test_gemini(api_key):
    model=gemini_model()
    url=f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    payload={'contents':[{'role':'user','parts':[{'text':'Reply exactly: RAN-NEETI API connection successful.'}]}], 'generationConfig':{'temperature':0,'maxOutputTokens':40}}
    r=requests.post(url,headers={'x-goog-api-key':api_key,'Content-Type':'application/json'},json=payload,timeout=(15,60))
    if r.status_code>=400:
        try: msg=r.json().get('error',{}).get('message',r.text)
        except Exception: msg=r.text
        raise RuntimeError(f'Gemini API {r.status_code}: {msg}')
    data=r.json()
    if not data.get('candidates'): raise RuntimeError('API accepted the key but returned no candidate response.')
    return model

def call_gemini(prompt, api_key):
    """Free-tier-compatible text generation: deliberately no Google Search grounding tool."""
    model = gemini_model()
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    payload = {
        'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.25, 'maxOutputTokens': 8192}
    }
    try:
        r = requests.post(url, headers={'x-goog-api-key': api_key, 'Content-Type': 'application/json'}, json=payload, timeout=(20, 180))
    except requests.RequestException as exc:
        raise RuntimeError(f'Gemini network error: {exc}') from exc
    if r.status_code >= 400:
        try:
            error = r.json().get('error', {})
            msg = error.get('message', r.text)
            status = error.get('status', '')
        except Exception:
            msg, status = r.text, ''
        if r.status_code == 429:
            raise RuntimeError('Gemini returned 429 (rate limit/quota). Search Grounding is disabled in this build. Check AI Studio API quota, free-tier model availability, and requests-per-minute limits. Details: ' + msg)
        if r.status_code in (401, 403):
            raise RuntimeError(f'Gemini authentication/permission error ({r.status_code}): {msg}')
        raise RuntimeError(f'Gemini API {r.status_code} {status}: {msg}')
    try:
        data = r.json()
    except ValueError as exc:
        raise RuntimeError('Gemini returned an invalid JSON response.') from exc
    candidates = data.get('candidates') or []
    if not candidates:
        reason = (data.get('promptFeedback') or {}).get('blockReason') or 'No candidate returned.'
        raise RuntimeError(f'Gemini did not return an analysis: {reason}')
    candidate = candidates[0]
    answer = '\n\n'.join(p.get('text', '') for p in (candidate.get('content') or {}).get('parts', []) if p.get('text'))
    if not answer.strip():
        finish = candidate.get('finishReason', 'unknown')
        raise RuntimeError(f'Gemini returned an empty report (finish reason: {finish}). Try a shorter prompt or check model quota.')
    # Sources are gathered from the app's public lookup APIs, not fabricated by the model.
    return answer, [], model

def build_prompt(domain, details, context, detail, entity_notes):
    return f'''You are RAN-NEETI, an evidence-aware academic matchup research assistant. Analyse the exact matchup using the supplied public-source records and user context. No live Google Search grounding is enabled. Never fabricate facts, citations, statistics, injuries, lineups, dates, feats, or source links. Clearly distinguish verified facts, reasonable inference, and uncertainty.

DOMAIN: {domain}
MATCHUP DETAILS: {details}
USER CONTEXT / RULES: {context or 'Not supplied'}
ENTITY LOOKUP NOTES (candidate records are identification aids, not proof of current performance):\n{entity_notes or 'No external entity record was selected.'}
ANALYSIS DEPTH: {detail}

Return a structured report with these sections:
1. MATCHUP IDENTIFICATION: exact entities, sport/format or fictional universe/version, event/date only if verified; flag ambiguity.
2. EVIDENCE & CURRENT CONTEXT: for sports, recent results/form, head-to-head only if relevant, roster/injury/availability, venue/weather/conditions and key stats only when supported by current sources. For fiction, canon/version, sourced abilities, feats and limitations.
3. OUTCOME ESTIMATE: probabilities summing to 100% using appropriate outcome categories. For football include draw when relevant; for other sports use valid outcomes. Label as qualitative AI estimate unless a validated statistical model and measured output are actually supplied. Never invent a model accuracy.
4. WHY: advantages, strengths, weaknesses and matchup edges for both sides.
5. MAJOR MOVES / GAME-CHANGERS: likely decisive actions/strategies for each side, timing/trigger, likely impact, risk and opponent counter. Fictional abilities must be supported by the selected canon/version.
6. TURNING POINTS: specific events or conditions that could change the outcome.
7. WIN CONDITIONS: what each side needs to do, plausible path to victory and how the opponent can disrupt it.
8. OUTCOME PATHS: explain how each plausible result could happen.
9. WHAT COULD CHANGE THE ESTIMATE: missing data, uncertain assumptions, late updates, alternate versions/rules.
10. SOURCES & FRESHNESS: cite source names/links in the text and state publication/retrieval dates when available.

For sports, do not imply the app has a live official data feed. Public entity metadata may be stale or incomplete; state clearly when recent results, injuries, lineups, venue conditions or current data were not supplied or independently verified. For fiction, probabilities are subjective scenario interpretations, not empirically measurable forecasts. Keep the answer detailed, readable, and useful. Do not use betting odds or wagering language.'''

def save_report(title, domain, report, sources, model):
    entry={'title':title,'domain':domain,'report':report,'sources':sources,'model':model,'time':datetime.now(timezone.utc).isoformat()}
    st.session_state.setdefault('report_history',[]).insert(0,entry)
    st.session_state['active_report']=entry

# ----------------------------- Sidebar / navigation -----------------------------
with st.sidebar:
    st.markdown('## ⚔️ RAN-NEETI')
    page=st.radio('Navigation',['Home Dashboard','Real Sports Lab','Anime & Fictional Battles','Recent Reports','About RAN-NEETI'],key='nav_page',label_visibility='collapsed')
    st.divider()
    st.markdown('### API connection')
    key=get_secret('GEMINI_API_KEY')
    if key: st.success('Gemini API key detected')
    else: st.warning('Gemini API key not configured')
    if st.button('TEST API CONNECTION',use_container_width=True):
        if not key: st.error('Add GEMINI_API_KEY in Streamlit Cloud → App settings → Secrets.')
        else:
            try: st.success('Connected: '+test_gemini(key))
            except Exception as e: st.error(str(e))
    st.caption('Model: '+gemini_model())
    st.divider()
    st.caption('AI estimates are not validated statistical forecasts. Inspect sources and uncertainty.')

# ----------------------------- Shared display -----------------------------
def hero(kicker, subtitle):
    st.markdown(f'<div class="hero"><div class="kicker">{kicker}</div><div class="brand">RAN-NEETI</div><p style="color:#b8c6df;font-size:16px">{subtitle}</p></div>',unsafe_allow_html=True)

def show_lookup_card(record, label):
    if not record: return
    with st.container(border=True):
        a,b=st.columns([1,3])
        with a:
            if record.get('image'): st.image(record['image'],use_container_width=True)
        with b:
            st.markdown('**'+label+' — '+record.get('title','')+'**')
            st.caption(record.get('source','')+' entity lookup')
            if record.get('extract'): st.write(record['extract'][:850]+('…' if len(record['extract'])>850 else ''))
            if record.get('url'): st.markdown('[Open source record]('+record['url']+')')

def render_report(entry):
    st.markdown('---')
    st.markdown('## 📡 Matchup intelligence report')
    st.caption(f"{entry['title']}  •  {entry['domain']}  •  {entry['model']}  •  {entry['time']}")
    st.markdown(entry['report'])
    if entry.get('sources'):
        st.markdown('### 🔗 Grounding sources')
        for i,s in enumerate(entry['sources'],1): st.markdown(f"{i}. [{s['title']}]({s['url']})")
    else: st.info('No external entity-source links were returned. Verify current facts independently.')
    export='# RAN-NEETI Matchup Report\n\n'+f"**Matchup:** {entry['title']}\n\n**Domain:** {entry['domain']}\n\n**Generated:** {entry['time']}\n\n"+entry['report']+'\n\n## Sources\n'+'\n'.join(f"- [{s['title']}]({s['url']})" for s in entry.get('sources',[]))
    st.download_button('⬇️ Download this report (.md)',data=export,file_name='ran_neeti_report.md',mime='text/markdown',key='download_'+str(abs(hash(entry['time']))))

# ----------------------------- Pages -----------------------------
if page=='Home Dashboard':
    hero('MULTI-SPORT • SEARCH-GROUNDED AI • FICTIONAL MATCHUPS','One matchup in. Research, evidence, outcome estimates, major moves, counters, turning points and win conditions out.')
    st.markdown('### Choose your analysis workspace')
    c1,c2=st.columns(2)
    with c1:
        st.markdown('<div class="panel"><h3>🏟️ Real Sports Lab</h3><p>Compare teams, athletes or competitors across a wide range of sports. Add match format, venue, event date and context.</p></div>',unsafe_allow_html=True)
        st.button('OPEN REAL SPORTS LAB',use_container_width=True,on_click=lambda: st.session_state.update({'nav_page':'Real Sports Lab'}))
    with c2:
        st.markdown('<div class="panel"><h3>⚔️ Anime & Fictional Battles</h3><p>Compare characters with universe, version, story arc and scenario rules clearly specified.</p></div>',unsafe_allow_html=True)
        st.button('OPEN FICTIONAL BATTLES',use_container_width=True,on_click=lambda: st.session_state.update({'nav_page':'Anime & Fictional Battles'}))
    st.markdown('### Analysis pipeline')
    cols=st.columns(4)
    for col,title,body in zip(cols,['01 · Identify','02 · Retrieve','03 · Analyse','04 · Explain'],['Resolve the selected teams, athletes or characters.','Retrieve public entity information from available APIs.','Compare evidence, strengths, risks, moves and counters.','Present outcome paths, uncertainty and source links.']):
        with col: st.markdown(f'<div class="panel"><b>{title}</b><p>{body}</p></div>',unsafe_allow_html=True)
    if st.session_state.get('report_history'):
        st.markdown('### Recent activity')
        for item in st.session_state['report_history'][:3]: st.write('• '+item['title']+' — '+item['time'])
    st.info('Important: broad sport coverage means the AI can research many sports; it does not mean a separate trained ML model exists for every sport. Percentages remain qualitative AI estimates until independently validated.')

elif page=='Real Sports Lab':
    hero('REAL SPORTS LAB • MULTI-SPORT ANALYSIS','Compare two sides with sport-specific context, current research, tactical factors and transparent uncertainty.')
    with st.form('sports_form'):
        c1,c2,c3=st.columns(3)
        with c1: sport=st.selectbox('Sport / competition',ALL_SPORTS,index=ALL_SPORTS.index('Cricket (T20)'))
        with c2: match_format=st.text_input('Match format / event',placeholder='e.g. T20, best of 5, Grand Prix, league match')
        with c3: venue=st.text_input('Venue / conditions',placeholder='e.g. Wankhede, home/away, indoor, neutral venue')
        a,b=st.columns(2)
        with a: side_a=st.text_input('SIDE A',placeholder='e.g. India / Novak Djokovic')
        with b: side_b=st.text_input('SIDE B',placeholder='e.g. Australia / Carlos Alcaraz')
        c4,c5=st.columns(2)
        with c4: competition=st.text_input('Competition / tournament',placeholder='e.g. World Cup, Wimbledon, IPL')
        with c5: event_date=st.text_input('Match date (optional)',placeholder='e.g. 17 November 2026')
        context=st.text_area('Additional match context',placeholder='Lineups, player availability, weather, toss, rules, stage of tournament, or other context…')
        advanced=st.text_area('Advanced instructions (optional)',placeholder='e.g. Focus on bowling matchups, powerplay, death overs and venue dimensions…')
        detail=st.select_slider('Analysis depth',options=['Concise','Detailed','Deep research'],value='Detailed')
        submitted=st.form_submit_button('⚡ RESEARCH & ANALYSE MATCHUP',use_container_width=True)
    if submitted:
        if not side_a.strip() or not side_b.strip(): st.warning('Side A aur Side B dono enter karo.')
        elif side_a.strip().casefold()==side_b.strip().casefold(): st.warning('Side A aur Side B alag hone chahiye.')
        elif not key: st.error('Gemini API key missing. Add GEMINI_API_KEY in Streamlit Cloud → App settings → Secrets.')
        else:
            title=f'{side_a.strip()} vs {side_b.strip()}'
            with st.spinner('Entity records aur current search evidence retrieve ho rahe hain; analysis generate ho raha hai…'):
                try:
                    lookup_a=lookup_candidates(side_a,False); time.sleep(0.3); lookup_b=lookup_candidates(side_b,False)
                    note=[]
                    for label,res in [('Side A',lookup_a),('Side B',lookup_b)]:
                        if isinstance(res,list) and res: note.append(label+': '+res[0]['title']+' | '+res[0].get('extract','')[:500]+' | '+res[0].get('url',''))
                        else: note.append(label+': no matching entity metadata found; use only user-provided context and clearly flag uncertainty.')
                    details=f'Sport: {sport}; Format: {match_format or "not specified"}; Venue: {venue or "not specified"}; Side A: {side_a}; Side B: {side_b}; Competition: {competition or "not specified"}; Date: {event_date or "not specified"}'
                    prompt=build_prompt('REAL-WORLD SPORT',details,'; '.join(x for x in [context,advanced] if x),detail,'\n'.join(note))
                    report,_,model=call_gemini(prompt,key)
                    sources=[]
                    for rec in (lookup_a if isinstance(lookup_a,list) else []) + (lookup_b if isinstance(lookup_b,list) else []):
                        if rec.get('url') and not any(x['url']==rec['url'] for x in sources): sources.append({'title':rec.get('title') or rec['source'],'url':rec['url']})
                    save_report(title,'Real Sports — '+sport,report,sources,model)
                    st.success('Analysis generated.')
                    show_lookup_card(lookup_a[0] if isinstance(lookup_a,list) and lookup_a else None,'Side A')
                    show_lookup_card(lookup_b[0] if isinstance(lookup_b,list) and lookup_b else None,'Side B')
                except Exception as e: st.error('Analysis could not be completed: '+str(e))
    if st.session_state.get('active_report') and st.session_state['active_report']['domain'].startswith('Real Sports'): render_report(st.session_state['active_report'])
    with st.expander('Supported sport categories'):
        for group,items in SPORTS.items(): st.markdown('**'+group+'**  \n'+', '.join(items))

elif page=='Anime & Fictional Battles':
    hero('ANIME & FICTIONAL BATTLES • CHARACTER ANALYSIS','Compare characters with explicit canon, versions, story arcs and scenario rules. Interpretations remain conditional.')
    with st.form('fiction_form'):
        c1,c2=st.columns(2)
        with c1: matchup_type=st.selectbox('Matchup category',FICTION_TYPES)
        with c2: universe=st.text_input('Universe / franchise',placeholder='e.g. Naruto, Dragon Ball, Marvel')
        a,b=st.columns(2)
        with a: char_a=st.text_input('CHARACTER / FIGHTER A',placeholder='e.g. Naruto Uzumaki')
        with b: char_b=st.text_input('CHARACTER / FIGHTER B',placeholder='e.g. Sasuke Uchiha')
        c3,c4=st.columns(2)
        with c3: version_a=st.text_input('Side A version / story arc',placeholder='e.g. Six Paths, final arc')
        with c4: version_b=st.text_input('Side B version / story arc',placeholder='e.g. Rinnegan, final arc')
        rules=st.text_area('Scenario / battle rules',placeholder='e.g. neutral arena, no outside help, knowledge allowed, standard equipment…')
        context=st.text_area('Additional instructions (optional)',placeholder='e.g. Compare canon feats only; separate manga and anime feats…')
        detail=st.select_slider('Analysis depth',options=['Concise','Detailed','Deep research'],value='Deep research')
        submitted=st.form_submit_button('⚔️ ANALYSE FICTIONAL MATCHUP',use_container_width=True)
    if submitted:
        if not char_a.strip() or not char_b.strip(): st.warning('Dono character names enter karo.')
        elif char_a.strip().casefold()==char_b.strip().casefold(): st.warning('Dono characters alag hone chahiye.')
        elif not key: st.error('Gemini API key missing. Add GEMINI_API_KEY in Streamlit Cloud → App settings → Secrets.')
        else:
            title=f'{char_a.strip()} vs {char_b.strip()}'
            with st.spinner('Character metadata aur canon references retrieve ho rahe hain…'):
                try:
                    lookup_a=lookup_candidates(char_a,True); time.sleep(0.45); lookup_b=lookup_candidates(char_b,True)
                    note=[]
                    for label,res in [('Character A',lookup_a),('Character B',lookup_b)]:
                        if isinstance(res,list) and res: note.append(label+': '+res[0]['title']+' | '+res[0].get('extract','')[:650]+' | '+res[0].get('url',''))
                        else: note.append(label+': no matching character record found; flag canon identity as unverified.')
                    details=f'Type: {matchup_type}; Universe: {universe or "not specified"}; Character A: {char_a}; A version: {version_a or "not specified"}; Character B: {char_b}; B version: {version_b or "not specified"}; Scenario rules: {rules or "not specified"}'
                    prompt=build_prompt('FICTIONAL / ANIME MATCHUP',details,context,'Deep research' if detail=='Deep research' else detail,'\n'.join(note))
                    report,_,model=call_gemini(prompt,key)
                    sources=[]
                    for rec in (lookup_a if isinstance(lookup_a,list) else []) + (lookup_b if isinstance(lookup_b,list) else []):
                        if rec.get('url') and not any(x['url']==rec['url'] for x in sources): sources.append({'title':rec.get('title') or rec['source'],'url':rec['url']})
                    save_report(title,'Fictional — '+matchup_type,report,sources,model)
                    st.success('Fictional matchup analysis generated.')
                    show_lookup_card(lookup_a[0] if isinstance(lookup_a,list) and lookup_a else None,'Character A')
                    show_lookup_card(lookup_b[0] if isinstance(lookup_b,list) and lookup_b else None,'Character B')
                except Exception as e: st.error('Analysis could not be completed: '+str(e))
    if st.session_state.get('active_report') and st.session_state['active_report']['domain'].startswith('Fictional'): render_report(st.session_state['active_report'])

elif page=='Recent Reports':
    hero('SESSION ARCHIVE • RECENT REPORTS','Review reports generated in this active browser session and export them as Markdown.')
    history=st.session_state.get('report_history',[])
    if not history: st.info('Abhi is session mein koi report generate nahi hui. Sports Lab ya Fictional Battles se analysis run karo.')
    else:
        for i,item in enumerate(history):
            with st.expander(f"{item['title']}  |  {item['domain']}  |  {item['time']}",expanded=(i==0)):
                st.markdown(item['report'])
                if item.get('sources'):
                    st.markdown('**Sources**')
                    for s in item['sources']: st.markdown(f"- [{s['title']}]({s['url']})")
                content='# RAN-NEETI Report\n\n'+item['title']+'\n\n'+item['report']+'\n\n## Sources\n'+'\n'.join(f"- [{s['title']}]({s['url']})" for s in item.get('sources',[]))
                st.download_button('Download report',content,file_name=f'ran_neeti_report_{i+1}.md',mime='text/markdown',key=f'history_download_{i}')
        if st.button('CLEAR SESSION REPORT HISTORY'):
            st.session_state['report_history']=[]; st.session_state.pop('active_report',None); st.rerun()
    st.caption('Reports are stored in Streamlit session state only. They are not a permanent database and may disappear when the session resets.')

elif page=='About RAN-NEETI':
    hero('PROJECT INFORMATION • VIT ONLINE M.SC. DATA SCIENCE','A modular AI-assisted research and matchup-reporting application.')
    st.markdown('### Project overview')
    st.write('RAN-NEETI supports two separate analysis workflows: real-world sports and fictional/anime matchups. It combines a Streamlit interface, public entity metadata lookup and Gemini text generation. Google Search grounding is intentionally disabled for free-tier compatibility.')
    st.markdown('### Technology stack')
    tech=[('Python','Application logic and HTTP requests'),('Streamlit','Web interface, navigation, forms, session history and downloads'),('Requests','External API communication'),('Gemini API','Structured AI-assisted matchup analysis'),('TheSportsDB API','Public team and player entity metadata'),('Jikan API','Anime character metadata and portraits'),('MediaWiki API','General entity page, thumbnail and extract lookup')]
    for name,desc in tech: st.markdown(f'- **{name}:** {desc}')
    st.markdown('### Academic and responsible-use note')
    st.warning('This application is an AI-assisted research and reporting prototype, not a validated multi-sport machine-learning prediction system. The current software does not contain trained sport-specific models, a historical training pipeline, probability calibration experiments or measured accuracy results. Sports percentages are qualitative AI estimates. Fictional matchup percentages are subjective scenario interpretations.')
    st.markdown('### Current limitations')
    st.markdown('- External APIs can be unavailable, rate-limited or incomplete.\n- Google Search grounding is disabled; current news, live scores, injuries and lineups are not automatically verified.\n- Entity lookup initially selects the first returned record; always verify it.\n- Public entity metadata improves identification but does not verify current form, injuries or live match conditions.\n- Report history is session-only.\n- A live deployment and end-to-end runtime test must be verified separately.')
    st.markdown('### Project details')
    st.markdown('**Project:** RAN-NEETI: A Generalizable AI Framework for Probabilistic Outcome Prediction in Sports and Beyond  \n**Programme:** Online M.Sc. Data Science  \n**Institution:** Vellore Institute of Technology  \n**Course:** OLMDS699 – Project  \n**Semester:** Fall Semester 2026–27')
    st.markdown('### Documentation')
    st.markdown('- [Gemini API](https://ai.google.dev/gemini-api/docs)\n- [TheSportsDB API](https://www.thesportsdb.com/api.php)\n- [Jikan REST API](https://docs.api.jikan.moe/)\n- [MediaWiki API](https://www.mediawiki.org/wiki/API:Search)\n- [Streamlit documentation](https://docs.streamlit.io/)')

st.markdown('<hr><p class="small">RAN-NEETI • VIT Online M.Sc. Data Science Capstone • Evidence-aware AI analysis</p>',unsafe_allow_html=True)
