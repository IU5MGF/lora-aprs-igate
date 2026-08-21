
function updateClock(){document.getElementById('clock').textContent=new Date().toLocaleTimeString('it-IT')}
setInterval(updateClock,1000);
updateClock();

function rssiClass(r){
  if(!r) return '';
  if(r>-110) return 'rssi-good';
  if(r>-125) return 'rssi-ok';
  return 'rssi-bad';
}

async function loadStats(){
  try{
    const d = await (await fetch('/api/stats')).json();
    document.getElementById('stat-total').textContent = d.total;
    document.getElementById('stat-unique').textContent = d.unique;
    document.getElementById('stat-dist').textContent = d.best_distance || '-';
    document.getElementById('stat-dist').textContent = d.best_distance ? d.best_distance+' km' : '-';
    document.getElementById('stat-dist-call').textContent = d.best_callsign || '-';
    document.getElementById('stat-rssi').textContent = d.rssi_avg || '-';
    document.getElementById('stat-crc').textContent = d.crc_errors;
    document.getElementById('stat-meshcom').textContent = d.meshcom_packets;
    document.getElementById('stat-update').textContent = new Date().toLocaleTimeString('it-IT',{hour:'2-digit',minute:'2-digit'});
  }catch(e){console.error(e);}
}

async function loadPackets(){
  try{
    const hoursSel = document.getElementById('packets-hours');
    const hours = hoursSel ? hoursSel.value : '';
    const url = hours ? '/api/packets?hours='+hours : '/api/packets';
    const data = await (await fetch(url)).json();
    document.getElementById('packets-count').textContent = data.length+' PKT';
    const tbody = document.getElementById('packets-body');
    const prevFirst = tbody.querySelector('tr') ? tbody.querySelector('tr').dataset.time : null;
    tbody.innerHTML = '';
    data.forEach(function(p,i){
      const isNew = i===0 && p.time !== prevFirst;
      const tr = document.createElement('tr');
      if(isNew) tr.classList.add('new-packet');
      tr.dataset.time = p.time;
      const rssi_str = p.rssi ? p.rssi+' dBm' : '--';
      const snr_str = p.snr ? p.snr+' dB' : '--';
      const dist_str = p.distance ? p.distance+' km' : '--';
      let pathBadge;
      if(p.path && p.path.startsWith('MESHCOM:')){
        const meshParts = p.path.split(':')[1].split('*');
        const meshType = meshParts[0];
        const meshLabel = meshParts.length > 1 ? meshType+' via '+meshParts[1] : meshType;
        const meshClass = meshParts.length > 1 ? 'path-meshcom-digi' : 'path-meshcom';
        pathBadge = '<span class="path-badge '+meshClass+'" title="'+p.path+'">'+meshLabel+'</span>';
      }
      else if(p.path && p.path.includes('*')){
        const parts = p.path.split(',');
        const digiIdx = parts.findIndex(x => x.includes('*'));
        let digiCall = digiIdx >= 0 ? parts[digiIdx].replace('*','') : null;
        if(digiCall && /^(WIDE|TRACE|RELAY)\d*-?\d*$/.test(digiCall) && digiIdx > 0)
          digiCall = parts[digiIdx-1].replace('*','');
        const digiLabel = digiCall ? 'DIGI via '+digiCall : 'DIGI';
        pathBadge = '<span class="path-badge path-digi" title="'+p.path+'">'+digiLabel+'</span>';
      }
      else
        pathBadge = '<span class="path-badge path-rf">RF</span>';
      const isMeshRelay = p.path && p.path.startsWith('MESHCOM:') && p.path.includes('*');
      const isMeshDirect = p.path && p.path.startsWith('MESHCOM:') && !p.path.includes('*');
      const callDisplay = isMeshRelay
        ? '<span style="color:#ff8c00;font-weight:bold">'+p.callsign+'</span>'
        : isMeshDirect
        ? '<span style="color:#bc8cff;font-weight:bold">'+p.callsign+'</span>'
        : '<span class="callsign">'+p.callsign+'</span>';
      tr.innerHTML = '<td style="color:var(--text-dim)">'+p.time+'</td>'
        +'<td>'+callDisplay+'</td>'
        +'<td class="'+rssiClass(p.rssi)+'">'+rssi_str+'</td>'
        +'<td style="color:var(--text-dim)">'+snr_str+'</td>'
        +'<td>'+dist_str+'</td>'
        +'<td>'+pathBadge+'</td>'
        +'<td style="color:var(--text-dim);font-size:10px">'+p.comment+'</td>';
      tbody.appendChild(tr);
    });
  }catch(e){console.error(e);}
}

let stationMode = 'rf';

function setStationMode(mode){
  stationMode = mode;
  const btnRf = document.getElementById('btn-rf');
  const btnDigi = document.getElementById('btn-digi');
  if(mode === 'rf'){
    btnRf.style.background = 'var(--accent)';
    btnRf.style.color = 'var(--bg)';
    btnRf.style.border = 'none';
    btnDigi.style.background = 'var(--bg)';
    btnDigi.style.color = 'var(--text-dim)';
    btnDigi.style.border = '1px solid var(--border)';
  } else {
    btnDigi.style.background = 'var(--accent3)';
    btnDigi.style.color = 'var(--bg)';
    btnDigi.style.border = 'none';
    btnRf.style.background = 'var(--bg)';
    btnRf.style.color = 'var(--text-dim)';
    btnRf.style.border = '1px solid var(--border)';
  }
  loadTopStations();
}

async function loadTopStations(){
  try{
    const url = stationMode === 'rf' ? '/api/top_stations' : '/api/top_stations_digi';
    const data = await (await fetch(url)).json();
    const max = data[0] ? data[0].count : 1;
    const el = document.getElementById('top-stations');
    el.innerHTML = '';
    if(data.length === 0){
      el.innerHTML = '<div style="padding:16px;font-family:var(--mono);font-size:11px;color:var(--text-dim)">Nessuna stazione</div>';
      return;
    }
    const color = stationMode === 'rf' ? 'var(--accent)' : 'var(--accent3)';
    data.forEach(function(s,i){
      const div = document.createElement('div');
      div.className = 'station-row';
      div.innerHTML = '<span class="station-rank">'+(i+1)+'</span>'
        +'<span class="station-call" style="color:'+color+'">'+s.callsign+'</span>'
        +'<div class="station-bar-wrap"><div class="station-bar" style="width:'+(s.count/max*100)+'%;background:'+color+'"></div></div>'
        +'<span class="station-count">'+s.count+' pkt</span>'
        +'<span class="station-dist">'+s.max_distance+' km</span>';
      el.appendChild(div);
    });
  }catch(e){console.error(e);}
}

async function loadHourly(){
  try{
    const data = await (await fetch('/api/hourly')).json();
    const now = new Date();
    const currentHour = now.getHours();
    // tutte le 24 ore, ora corrente evidenziata
    const hours = [];
    for(let h=0; h<24; h++) hours.push(h.toString().padStart(2,'0'));
    const vals = hours.map(h => data[h] || 0);
    const max = Math.max.apply(null, vals.concat([1]));
    const avg = vals.reduce((a,b)=>a+b,0) / (vals.length || 1);
    const el = document.getElementById('chart-bars');
    el.innerHTML = '';
    // contenitore con posizione relativa per la linea guida
    const wrap = document.createElement('div');
    wrap.style.cssText = 'position:relative;display:flex;align-items:flex-end;height:160px;gap:3px;width:100%';
    // linea guida media
    const avgH = avg/max*140;
    const guideline = document.createElement('div');
    guideline.style.cssText = 'position:absolute;left:0;right:0;bottom:'+(avgH+20)+'px;border-top:1px dashed rgba(0,212,255,0.3);z-index:1;pointer-events:none';
    const guideLabel = document.createElement('span');
    guideLabel.style.cssText = 'position:absolute;right:0;top:-14px;font-family:var(--mono);font-size:8px;color:rgba(0,212,255,0.5)';
    guideLabel.textContent = 'avg '+Math.round(avg);
    guideline.appendChild(guideLabel);
    wrap.appendChild(guideline);
    hours.forEach(function(hr){
      const cnt = data[hr] || 0;
      const isCurrent = parseInt(hr) === currentHour;
      const div = document.createElement('div');
      div.className = 'chart-bar-col';
      div.style.cssText = 'flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;height:100%;justify-content:flex-end;position:relative;z-index:2';
      const h = cnt > 0 ? Math.max(cnt/max*140, 4) : 0;
      div.innerHTML = '<div style="font-family:var(--mono);font-size:8px;color:var(--text-dim);text-align:center">'+(cnt > 0 ? cnt : '')+'</div>'
        +'<div class="chart-bar '+(isCurrent?'current':'')+'" style="height:'+h+'px"></div>'
        +'<span class="chart-label">'+hr+'</span>';
      wrap.appendChild(div);
    });
    el.appendChild(wrap);
  }catch(e){console.error(e);}
}


async function loadStationsPreview(){
  try{
    const data = await (await fetch('/api/stations')).json();
    const top5 = data.slice(0,5);
    const max = top5[0] ? top5[0].total_packets : 1;
    const el = document.getElementById('stations-preview');
    el.innerHTML = '';
    top5.forEach(function(s,i){
      const div = document.createElement('div');
      div.className = 'station-row';
      div.innerHTML = '<span class="station-rank">'+(i+1)+'</span>'
        +'<span class="station-call">'+s.callsign+'</span>'
        +'<div class="station-bar-wrap"><div class="station-bar" style="width:'+(s.total_packets/max*100)+'%"></div></div>'
        +'<span class="station-count">'+s.total_packets+' pkt</span>'
        +'<span class="station-dist">'+(s.max_distance ? s.max_distance+' km' : '-')+'</span>';
      el.appendChild(div);
    });
  }catch(e){console.error(e);}
}

async function loadBeacon(){
  try{
    const d = await (await fetch('/api/igate_beacon')).json();
    const timeEl = document.getElementById('stat-beacon-time');
    const unitEl = document.getElementById('stat-beacon-unit');
    const dotEl = document.getElementById('beacon-dot');
    if(timeEl) timeEl.textContent = d.time;
    if(unitEl) unitEl.textContent = d.online ? d.minutes_ago+' min fa' : 'OFFLINE';
    if(dotEl){
      const circle = document.getElementById('beacon-dot-circle');
      const color = d.online ? 'var(--accent3)' : '#4a6070';
      if(circle){ circle.style.background = color; circle.style.boxShadow = '0 0 5px '+color; }
    }
    const card = timeEl ? timeEl.closest('.stat-card') : null;
    if(card) card.style.borderTopColor = d.online ? 'var(--accent3)' : 'var(--accent2)';
  }catch(e){console.error(e);}
}
async function refresh(){
  await Promise.all([loadStats(), loadPackets(), loadTopStations(), loadHourly(), loadStationsPreview(), loadBeacon()]);
}

refresh();
setInterval(refresh, 30000);
