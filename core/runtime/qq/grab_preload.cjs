// ElainaQQ grab preload（LiteLoaderQQNT-Grab-RedBag 同款路线，渲染进程）
// 订阅 nodeIKernelMsgListener/onRecvMsg -> 观察 wallet 元素（只记录，不领取）。
// 领取决策走插件策略链路；本文件仅提供插件显式下发的 grab-go / scan 任务执行器。
const { ipcRenderer } = require('electron');

const DOWN_MAIN2 = 'RM_IPCFROM_MAIN2';
let wcId = 0;
let nickName = '';
const grabbedBills = new Set();

function log(...args) {
  try {
    const text = args.map((a) => {
      try { return typeof a === 'object' ? JSON.stringify(a) : String(a); } catch { return String(a); }
    }).join(' ');
    try { ipcRenderer.send('elainaqq:grab-log', text); } catch {}
    try { ipcRenderer.send('elainaqq:grab-file', 'LOG ' + new Date().toISOString() + ' ' + text); } catch {}
  } catch {}
}

function invokeNative(eventName, cmdName, registered, ...args) {
  return new Promise((resolve, reject) => {
    const callbackId = `${Date.now()}_${Math.random().toString(16).slice(2)}`;
    const down = `RM_IPCFROM_MAIN${wcId}`;
    const callback = (_event, ...resultArgs) => {
      if (resultArgs?.[0]?.callbackId === callbackId) {
        try { ipcRenderer.off(down, callback); } catch {}
        try { ipcRenderer.off(DOWN_MAIN2, callback); } catch {}
        resolve(resultArgs[1]);
      }
    };
    try { ipcRenderer.on(down, callback); } catch {}
    try { ipcRenderer.on(DOWN_MAIN2, callback); } catch {}
    try {
      ipcRenderer.send(`RM_IPCFROM_RENDERER${wcId}`, {
        type: 'request', callbackId, eventName, peerId: String(wcId),
      }, { cmdName, cmdType: 'invoke', payload: args });
    } catch (error) {
      try { ipcRenderer.off(down, callback); } catch {}
      try { ipcRenderer.off(DOWN_MAIN2, callback); } catch {}
      reject(error);
    }
    setTimeout(() => {
      try { ipcRenderer.off(down, callback); } catch {}
      try { ipcRenderer.off(DOWN_MAIN2, callback); } catch {}
      reject(new Error('invoke timeout: ' + cmdName));
    }, 20000);
  });
}

function handleRecvMsg(payload) {
  try {
    if (!payload || !Array.isArray(payload.msgList) || !payload.msgList[0]) return;
    const msg = payload.msgList[0];
    let wallEl = null;
    for (const el of (msg.elements || [])) {
      if (el.elementType === 9 && el.walletElement) { wallEl = el.walletElement; break; }
    }
    if (!wallEl || !wallEl.billNo) return;
    // 渲染层只观察记录；领取决策走插件策略链路（框架桥事件 -> 插件监听器 -> grab API / grab-go 任务）。
    log('[grab] wallet observed', wallEl.billNo);
  } catch (e) {
    log('[grab] handler error', String(e));
  }
}

async function start() {
  try {
    const info = await ipcRenderer.invoke('elainaqq:whoami');
    wcId = info && info.wcId ? info.wcId : 0;
    nickName = (info && info.nickName) || '';
  } catch (e) {
    log('[grab] whoami error', String(e));
    return;
  }
  if (!wcId) { log('[grab] no wcId'); return; }
  log('[grab] preload active wcId=', wcId, 'nick=', nickName);

  // 诊断：记录 QQ preload 注册的所有 IPC 通道（找消息分发通道名）
  try {
    const origOn = ipcRenderer.on.bind(ipcRenderer);
    const seen = new Set();
    ipcRenderer.on = (ch, fn) => { seen.add(ch); return origOn(ch, fn); };
    setTimeout(() => {
      log('[grab] ipc channels seen:', Array.from(seen).join(','));
    }, 20000);
  } catch {}

  const down = `RM_IPCFROM_MAIN${wcId}`;
  let sawAny = false;
  // 群号→uid 缓存（从实时消息学习）；扫描任务待执行时，一有该群消息就触发补扫
  const learnedUids = new Map();
  let pendingScan = null;
  const listener = (_event, ...args) => {
    try {
      const cmd = (args && (args[1]?.cmdName || args[2]?.cmdName || (args[3] && args[3][1] && args[3][1].cmdName))) || '';
      if (cmd === 'nodeIKernelMsgListener/onRecvMsg') {
        const payload = args[1]?.payload || args[2]?.payload || (args[3] && args[3][1] && args[3][1].payload);
        if (!sawAny) { sawAny = true; log('[grab] first onRecvMsg seen, argIdx=', JSON.stringify(args)?.slice(0, 120)); }
        // 学习群号→uid 映射（实时消息的 peerUid 就是群 uid）
        try {
          const msg = payload && payload.msgList && payload.msgList[0];
          if (msg && Number(msg.chatType) === 2 && msg.peerUin && msg.peerUid && msg.peerUid.startsWith('u_')) {
            const isNew = !learnedUids.has(String(msg.peerUin));
            learnedUids.set(String(msg.peerUin), String(msg.peerUid));
            if (isNew) log('[grab] learned uid', msg.peerUin, '->', msg.peerUid);
            if (pendingScan && pendingScan.groupId === String(msg.peerUin)) {
              const t = pendingScan;
              pendingScan = null;
              log('[grab] deferred scan triggered by uid learned:', t.groupId);
              setTimeout(() => runScanTask(t), 2000);
            }
          }
        } catch {}
        handleRecvMsg(payload);
      }
    } catch {}
  };
  try { ipcRenderer.on(down, listener); } catch {}
  // 扫描执行体（uid 未学习到时挂起等待实时消息补扫）
  function runScanTask(task) {
    const groupId = task.scan.groupId;
    const count = task.scan.count;
    (async () => {
      let peerUid = learnedUids.get(String(groupId)) || '';
      if (!peerUid) {
        pendingScan = task;
        log('[grab] scan deferred: uid unknown for', groupId, '- waiting for a live message to learn uid');
        return;
      }
      log('[grab] scan run', groupId, 'uid=', peerUid);
      const fromTime = String(Math.floor(Date.now() / 1e3) - (task.scan.hours || 48) * 3600);
      let msgList = [];
      try {
        const res = await invokeNative('ntApi', 'nodeIKernelMsgService/queryMsgsWithFilterEx', false,
          '0', '0', '0', {
            chatInfo: { chatType: 2, peerUid, guildId: '' },
            filterMsgType: [],
            filterSendersUid: [],
            filterMsgToTime: '0',
            filterMsgFromTime: fromTime,
            isReverseOrder: true,
            isIncludeCurrent: true,
            pageLimit: Math.min(300, count || 100),
          });
        msgList = Array.isArray(res?.msgList) ? res.msgList : [];
        log('[grab] scan filterEx batch', msgList.length);
      } catch (e) { log('[grab] scan filterEx ERR', String(e)); }
      await collectAndGrab(msgList, groupId, count);
    })();
  }
  async function collectAndGrab(msgList, groupId, count) {
    if (msgList.length) {
      const pagePeer = { chatType: 2, peerUid: learnedUids.get(String(groupId)) || '', guildId: '' };
      let cursor = String(msgList[0]?.msgSeq ?? '');
      while (msgList.length < (count || 60) && cursor && cursor !== '0') {
        const batch = Math.min(60, (count || 60) - msgList.length);
        let older = [];
        try {
          const res = await invokeNative('ntApi', 'nodeIKernelMsgService/getMsgsBySeqAndCount', false, pagePeer, cursor, batch, true, true);
          older = Array.isArray(res?.msgList) ? res.msgList : [];
        } catch (e) { log('[grab] scan page ERR', String(e)); break; }
        if (!older.length) break;
        msgList = older.concat(msgList);
        cursor = String(older[0]?.msgSeq ?? '');
      }
    }
    let grabbed = 0;
    for (const msg of msgList) {
      for (const el of (msg.elements || [])) {
        if (el.elementType !== 9 || !el.walletElement) continue;
        const wallEl = el.walletElement;
        if (!wallEl.billNo || grabbedBills.has(wallEl.billNo)) continue;
        grabbedBills.add(wallEl.billNo);
        grabbed++;
        const grabRedBagReq = {
          recvUin: msg.chatType === 1 ? (msg.peerUin || msg.peerUid) : msg.peerUid,
          recvType: msg.chatType,
          peerUid: msg.peerUid,
          name: nickName,
          pcBody: wallEl.pcBody || '',
          wishing: (wallEl.receiver && wallEl.receiver.title) || '',
          msgSeq: msg.msgSeq,
          index: wallEl.stringIndex || '',
        };
        log('[grab] scan packet', wallEl.billNo, JSON.stringify(grabRedBagReq));
        try {
          const result = await invokeNative('ntApi', 'nodeIKernelMsgService/grabRedBag', false, { grabRedBagReq });
          log('[grab] scan grab result', JSON.stringify(result));
          const line = JSON.stringify({ at: new Date().toISOString(), source: 'scan', billNo: wallEl.billNo, result });
          try { ipcRenderer.send('elainaqq:grab-file', line); } catch {}
        } catch (e) { log('[grab] scan grab ERR', wallEl.billNo, String(e)); }
      }
    }
    const done = JSON.stringify({ at: new Date().toISOString(), source: 'scan-done', group: groupId, msgs: msgList.length, packets: grabbed });
    try { ipcRenderer.send('elainaqq:grab-file', done); } catch {}
    log('[grab] scan done', groupId, 'msgs=', msgList.length, 'packets=', grabbed);
  }
  // Plan B：接收 Python 侧下发的红包领取任务（经 loader 主进程转发）
  try {
    ipcRenderer.on('elainaqq:grab-go', (_ev, task) => {
      try {
        // 扫描任务：拉历史消息，提取 walletElement 后逐个领取
        if (task && task.scan) {
          log('[grab] scan task', task.scan.groupId, 'count=', task.scan.count);
          runScanTask(task);
          return;
        }
        log('[grab] grab-go task', JSON.stringify(task).slice(0, 400));
        const { nickName: nn, ...req } = task;
        const name = nn || nickName;
        invokeNative('ntApi', 'nodeIKernelMsgService/grabRedBag', false, {
          grabRedBagReq: { ...req, name },
        }).then((result) => {
          log('[grab] grab-go result', JSON.stringify(result));
          const line = JSON.stringify({ at: new Date().toISOString(), source: 'grab-go', task, result });
          try { ipcRenderer.send('elainaqq:grab-file', line); } catch {}
        }).catch((e) => log('[grab] grab-go invoke error', String(e)));
      } catch (e) { log('[grab] grab-go handler err', String(e)); }
    });
    log('[grab] grab-go listener installed');
  } catch {}
  try { ipcRenderer.on(DOWN_MAIN2, listener); } catch {}
  log('[grab] subscribed onRecvMsg, down=', down);
  // 健康探针：3 个不同类型的只读调用
  setTimeout(() => {
    invokeNative('ntApi', 'nodeIKernelMsgService/getMsgShelfOnlineStatus', false, {}).then(
      (r) => log('[grab] probe shelf:', JSON.stringify(r)?.slice(0, 200)),
      (e) => log('[grab] probe shelf ERR:', String(e)));
    invokeNative('ntApi', 'nodeIKernelMsgService/isSessionSpaceActivated', false, {}).then(
      (r) => log('[grab] probe activated:', JSON.stringify(r)?.slice(0, 200)),
      (e) => log('[grab] probe activated ERR:', String(e)));
  }, 8000);
  // 探针 v3：记录所有到达的 IPC 事件通道（60 秒窗口）
  try {
    const origEmit = ipcRenderer.emit.bind(ipcRenderer);
    const chanCount = new Map();
    ipcRenderer.emit = (ch, ...rest) => {
      if (typeof ch === 'string' && !ch.startsWith('elainaqq')) {
        chanCount.set(ch, (chanCount.get(ch) || 0) + 1);
      }
      return origEmit(ch, ...rest);
    };
    setTimeout(() => {
      const top = Array.from(chanCount.entries()).sort((a, b) => b[1] - a[1]).slice(0, 25);
      log('[grab] emit channels 60s:', JSON.stringify(top));
      const msgLike = top.filter(([k]) => /msg|Msg|push|Push|listener|Listener/.test(k));
      log('[grab] msg-like channels:', JSON.stringify(msgLike));
    }, 60000);
  } catch (e) { log('[grab] probe3 err', String(e)); }
  let dumped = 0;
  const origOnProbe = (...a) => {
    dumped++;
    if (dumped <= 6) log('[grab] DOWN traffic #' + dumped + ':', String(JSON.stringify(a)).slice(0, 700));
  };
  try { ipcRenderer.on(down, origOnProbe); } catch {}
  try { ipcRenderer.on(DOWN_MAIN2, origOnProbe); } catch {}
}

start();
