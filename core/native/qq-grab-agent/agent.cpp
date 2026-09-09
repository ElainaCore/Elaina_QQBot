// qq-grab-agent: injected into QQ.exe; captures KernelMsgService instance and
// invokes grabRedBag via QQ's own code paths. Frame protocol: 4B len + JSON
// over \\.\pipe\elaina_grab_agent.
//
// Wrapper RVA anchors are for QQ 9.9.35-52892 (wrapper.node, image base
// 0x180000000). See tools/wrapper_anchors.py for how they are derived.
#include <windows.h>
#ifdef __GNUC__
#define _ReturnAddress() ((void*)__builtin_return_address(0))
#endif

#ifdef __GNUC__
#endif

#include <cstdio>
#include <cstdint>
#include <cstring>
#include <string>
#include <deque>
#include <mutex>
#include <fstream>

// ---- RVAs (QQ 9.9.35-52892) -----------------------------------------------
static const uintptr_t kUnwrapSlotRva  = 0x4A4CAD8;
static const uintptr_t kUnwrapRetRva   = 0x100B405;
static const uintptr_t kAssembleRva    = 0x101ACD0;
static constexpr uint32_t kGrabInfoStrRva = 0x46FF9E6;  // "grab info, string_name=..." log format string
static const uintptr_t kStrFromPendRva = 0x32C4;
static const uintptr_t kStrDtorRva     = 0x290A;
static const uintptr_t kReqDtorRva     = 0x100BC26;
static const uintptr_t kGrabVtSlot     = 0x810;
static const size_t    kReqSize        = 0xA8;
static const size_t    kAsmStolenLen   = 12;  // 8x push + sub rsp,0x28 (4B)

typedef void* (__fastcall* FnAssemble)(void* dest, void* pcBody, void* index,
                                       void* pbReserve, void* name, void* wishing,
                                       uint64_t recvUin, void* peerUid,
                                       uint32_t recvType, uint64_t msgSeq);
typedef void* (__fastcall* FnStrFromPend)(void* dst, const void* srcPend);
typedef void  (__fastcall* FnStrDtor)(void* s);
typedef void  (__fastcall* FnReqDtor)(void* req);
typedef void* (*FnUnwrapThunk)(void* env, void* value, void** result);

// unwrap 调用点白名单（返回地址 RVA）：
//  0x100B405 - 服务拉取路径（早期定位）
//  0x1072512 - grabRedBag wrapper 实测点红包路径（09-05 诊断数组实锤）
static const uintptr_t kUnwrapRetRva2 = 0x1072512;
typedef void* (__fastcall* FnGrab)(void* self, void* req, void* cbSp);

static HMODULE  g_wrapper = nullptr;
static uintptr_t g_base   = 0;
static void* volatile g_inst = nullptr;
static FnUnwrapThunk g_origUnwrap = nullptr;
static void** g_unwrapSlot = nullptr;
static HANDLE g_pipe = INVALID_HANDLE_VALUE;
static volatile bool g_clientConnected = false;
static volatile bool g_asmHooked = false;   // forward: set by HookAssembleEntry
static CRITICAL_SECTION g_cs;   // serializes pipe writes + state flips

static void Dbg(const char* msg) { OutputDebugStringA(msg); }

#include <fstream>
static void TraceFile(const std::string& s) {
    static std::mutex tm;
    static std::ofstream tf("C:\\Users\\22188\\Documents\\GitHub\\Elaina_QQBot\\_agent_trace.log", std::ios::app);
    std::lock_guard<std::mutex> lk(tm);
    tf << s << std::endl;
}

static std::string EscapeJson(const std::string& s) {
    std::string o;
    o.reserve(s.size() + 16);
    for (unsigned char c : s) {
        switch (c) {
            case '"': o += "\\\""; break;
            case '\\': o += "\\\\"; break;
            case '\n': o += "\\n"; break;
            case '\r': o += "\\r"; break;
            case '\t': o += "\\t"; break;
            default:
                if (c < 0x20) { char b[8]; _snprintf_s(b, sizeof(b), _TRUNCATE, "\\u%04x", c); o += b; }
                else o += (char)c;
        }
    }
    return o;
}

// Event queue: hooks never touch the pipe (a blocking WriteFile on QQ's UI/JS
// thread would freeze the whole app when the client stalls). A dedicated
// writer thread drains the queue to the pipe. Simple mutex + deque: hooks are
// low-frequency, correctness beats lock-free cleverness here.
static std::deque<std::string> g_evQueue;

static void EnqueueEvent(std::string s) {
    EnterCriticalSection(&g_cs);
    if (g_evQueue.size() > 1024) g_evQueue.pop_front();  // drop oldest
    g_evQueue.push_back(std::move(s));
    LeaveCriticalSection(&g_cs);
}

static void SendEvent(const char* jsonLine) {
    Dbg(jsonLine);
    EnqueueEvent(std::string(jsonLine));
}

static void SendEventString(std::string s) {
    EnqueueEvent(std::move(s));
}

static bool PopEvent(std::string& out) {
    EnterCriticalSection(&g_cs);
    if (g_evQueue.empty()) { LeaveCriticalSection(&g_cs); return false; }
    out = std::move(g_evQueue.front());
    g_evQueue.pop_front();
    LeaveCriticalSection(&g_cs);
    return true;
}

static HANDLE g_evPipe = INVALID_HANDLE_VALUE;  // events pipe (server end)

static DWORD WINAPI EvWriterThread(LPVOID) {
    Dbg("[grab-agent] ev writer started");
    TraceFile("ev writer thread running");
    std::string ev;
    for (;;) {
        if (!PopEvent(ev)) { Sleep(15); continue; }
        HANDLE pipe;
        EnterCriticalSection(&g_cs);
        pipe = g_evPipe;
        LeaveCriticalSection(&g_cs);
        if (pipe == INVALID_HANDLE_VALUE) continue;  // no client: drop
        uint32_t n = (uint32_t)ev.size();
        DWORD w = 0;
        BOOL ok1 = WriteFile(pipe, &n, 4, &w, nullptr);
        if (!ok1) {
            TraceFile("ev write hdr err=" + std::to_string(GetLastError()));
            continue;  // drop; events are best-effort
        }
        if (n) {
            BOOL ok2 = WriteFile(pipe, ev.data(), n, &w, nullptr);
            if (!ok2) TraceFile("ev write body err=" + std::to_string(GetLastError()));
        }
    }
    return 0;
}

// ---- QQ string helpers ------------------------------------------------------
// QQ 9.9.35 string (24B): byte[0]&1 == 0 -> SSO (byte[0]=len*2, data at +1);
//                          byte[0]&1 == 1 -> heap {ptr(+0), ?(+8), end(+0x10)}.
static std::string ReadQQString(void* s) {
    std::string out;
    if (!s) return out;
    uint8_t* p = (uint8_t*)s;
    if (p[0] & 1) {
        const char* b = *(const char**)(p);
        const char* e = *(const char**)(p + 0x10);
        if (b && e && e > b && (size_t)(e - b) < (1 << 20)) out.assign(b, e - b);
    } else {
        size_t len = (size_t)p[0] >> 1;
        if (len < 24) out.assign((const char*)(p + 1), len);
    }
    return out;
}

// Builds a QQ string in-place using QQ's own ctor from {ptr,end} pair.
static bool MakeQQString(void* dst, const char* data, size_t len, FnStrFromPend fn) {
    if (!data && len) return false;
    const void* pend[2] = { data, data + len };
    fn(dst, pend);
    return true;
}

// ---- fake IGrabRedBagCallback ------------------------------------------------
static void __fastcall FakeCbDtor(void*) {}

static void __fastcall FakeOnGrabResult(void* self, int code, void* strA, void* objB) {
    std::string a = ReadQQString(strA);
    std::string b = ReadQQString(objB);
    char hex[128] = {0};
    if (objB) {
        uint8_t* p = (uint8_t*)objB;
        for (int i = 0; i < 40 && i < 127; ++i) {
            hex[2*i]   = "0123456789abcdef"[(p[i] >> 4) & 0xF];
            hex[2*i+1] = "0123456789abcdef"[p[i] & 0xF];
        }
        hex[80] = 0;
    }
    std::string line = "{\"event\":\"grab_result\",\"code\":" + std::to_string(code) +
                       ",\"data\":\"" + EscapeJson(a) +
                       "\",\"dataB\":\"" + EscapeJson(b) +
                       "\",\"objHex\":\"" + std::string(hex) + "\"}";
    SendEvent(line.c_str());
}

static void* g_cbVtable[2]   = { (void*)&FakeCbDtor, (void*)&FakeOnGrabResult };
static void* g_ctrlVtable[4] = { (void*)&FakeCbDtor, (void*)&FakeCbDtor,
                                 (void*)&FakeCbDtor, (void*)&FakeCbDtor };
static uint8_t g_ctrl[0x40];

static void InitCtrl() {
    memset(g_ctrl, 0, sizeof(g_ctrl));
    *(void**)g_ctrl = g_ctrlVtable;
    *(uint32_t*)(g_ctrl + 0x08) = 2;   // _Uses (never reaches 0)
    *(uint32_t*)(g_ctrl + 0x10) = 1;   // _Weaks
    *(void**)(g_ctrl + 0x18) = g_cbVtable;
}

// ---- instance capture ---------------------------------------------------------
static volatile LONG g_diagIdx = 0;
static uintptr_t g_diagRva[16] = {};

static void* __fastcall HookUnwrap(void* env, void* value, void** result) {
    void* ret = g_origUnwrap(env, value, result);
    void* ra = _ReturnAddress();
    if (g_base) {
        uintptr_t rva = (uintptr_t)ra - g_base;
        LONG idx = InterlockedExchangeAdd(&g_diagIdx, 1);
        g_diagRva[idx % 16] = rva;
        // napi_unwrap returns napi_status (0 = ok), NOT the object. The object
        // lands in *result. v6.2 bug: requiring non-zero `ret` meant a
        // successful unwrap (ret==0) was never captured.
        if ((rva == kUnwrapRetRva || rva == kUnwrapRetRva2) && result && *result) {
            InterlockedExchangePointer(&g_inst, *result);
            char line[128];
            _snprintf_s(line, sizeof(line), _TRUNCATE,
                        "{\"event\":\"instance\",\"addr\":\"%llu\"}",
                        (unsigned long long)(uintptr_t)*result);
            SendEvent(line);
        }
    }
    return ret;
}

static bool HookUnwrapSlot() {
    g_unwrapSlot = (void**)(g_base + kUnwrapSlotRva);
    void* orig = *g_unwrapSlot;
    if (!orig) { Dbg("[grab-agent] unwrap slot empty\n"); return false; }
    g_origUnwrap = (FnUnwrapThunk)orig;
    DWORD old;
    if (!VirtualProtect(g_unwrapSlot, sizeof(void*), PAGE_READWRITE, &old)) {
        Dbg("[grab-agent] VirtualProtect failed\n");
        return false;
    }
    *g_unwrapSlot = (void*)&HookUnwrap;
    VirtualProtect(g_unwrapSlot, sizeof(void*), old, &old);
    char line[128];
    _snprintf_s(line, sizeof(line), _TRUNCATE,
                "{\"event\":\"log\",\"msg\":\"hooked unwrap slot, orig=%llu\"}",
                (unsigned long long)(uintptr_t)orig);
    SendEvent(line);
    return true;
}

// ---- grab invocation -----------------------------------------------------------
// must run on a thread QQ tolerates; assemble+grab are called with QQ's own fns.
struct GrabParams {
    std::string pcBody, index, pbReserve, name, wishing, peerUid;
    uint64_t recvUin = 0, msgSeq = 0;
    uint32_t recvType = 0;
};

static void RunGrab(const GrabParams& gp) {
    void* inst = g_inst;
    if (!inst) { SendEvent("{\"event\":\"grab_result\",\"error\":\"instance not captured yet\"}"); return; }
    if (!g_asmHooked) { SendEvent("{\"event\":\"grab_result\",\"error\":\"assemble hook not installed\"}"); return; }

    // Object layout notes (QQ 9.9.35-52892, dump-verified 2026-09-05):
    //  - vtable+0x810 = GrabRedBagEntry(this, const ReqSp*, const CbSp*) outer
    //    wrapper: dynamic_pointer_casts the callback, packs {req_sp,cb_sp} into
    //    a task and forwards to impl vtable+0x530 (wrapper+0x35DCC6).
    //  - inst+0x810/+0x818 = QQ's OWN IGrabRedBagCallback shared_ptr members
    //    (getter at wrapper+0x33902). Reusing it keeps RTTI check happy and
    //    routes the result through QQ's native handler.
    //  - assemble(0x101ACD0) only builds the 0xA8 request object; sending is
    //    fully inside the vtable chain.
    void* vt = *(void**)inst;
    // --- v9: runtime vtable calibration -------------------------------
    // kGrabVtSlot (0x810) drifts between QQ builds. The real
    // GrabRedBagEntry is the vtable method that calls assemble()
    // (kAssembleRva). Scan slots for a function whose first 64 bytes
    // contain `call rel32 -> g_base + kAssembleRva`.
    auto slotHasAssembleCall = [&](void* fn) -> bool {
        if (!fn) return false;
        MEMORY_BASIC_INFORMATION m{};
        if (!VirtualQuery(fn, &m, sizeof(m)) || m.State != MEM_COMMIT ||
            (m.Protect & (PAGE_EXECUTE | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY)) == 0)
            return false;
        const uint8_t* code = (const uint8_t*)fn;
        const uint8_t* grabInfoStr = (const uint8_t*)(g_base + kGrabInfoStrRva);
        for (int i = 0; i + 7 <= 512; ++i) {
            // LEA r64, [rip+rel32]: 48 8D /r  or  4C 8D /r
            if (code[i] == 0x48 && code[i+1] == 0x8D && (code[i+2] & 0xC7) == 0x05) {
                int32_t rel;
                memcpy(&rel, code + i + 3, 4);
                if (code + i + 7 + rel == grabInfoStr) return true;
            }
            if (code[i] == 0x4C && code[i+1] == 0x8D && (code[i+2] & 0xC7) == 0x05) {
                int32_t rel;
                memcpy(&rel, code + i + 3, 4);
                if (code + i + 7 + rel == grabInfoStr) return true;
            }
        }
        return false;
    };
    void* grabEntry = nullptr;
    uint32_t calibratedSlot = kGrabVtSlot;
    for (uint32_t off = 0x10; off + 8 <= 0xA00; off += 8) {
        void* fn = *(void**)((uint8_t*)vt + off);
        if (slotHasAssembleCall(fn)) { grabEntry = fn; calibratedSlot = off; break; }
    }
    if (!grabEntry) {
        grabEntry = *(void**)((uint8_t*)vt + kGrabVtSlot);
        calibratedSlot = kGrabVtSlot;
    }
    {
        char msg[96];
        snprintf(msg, sizeof(msg), "{\"event\":\"log\",\"msg\":\"calibrated slot: 0x%X\"}", calibratedSlot);
        SendEvent(msg);
    }
    // ------------------------------------------------------------------

    void* cbPtr = *(void**)((uint8_t*)inst + 0x810);
    void* cbCtrl = *(void**)((uint8_t*)inst + 0x818);
    if (!cbPtr || !cbCtrl) { SendEvent("{\"event\":\"grab_result\",\"error\":\"callback sp not initialized on instance\"}"); return; }

    // Build request in a static buffer: the send path is asynchronous, so the
    // request object must outlive this call.
    static uint8_t reqBuf[kReqSize];
    static bool reqBufUsed = false;
    if (reqBufUsed) { SendEvent("{\"event\":\"grab_result\",\"error\":\"grab already in flight\"}"); return; }
    reqBufUsed = true;

    FnAssemble assemble = (FnAssemble)(g_base + kAssembleRva);
    FnStrFromPend mkstr = (FnStrFromPend)(g_base + kStrFromPendRva);
    FnReqDtor    rdtor  = (FnReqDtor)(g_base + kReqDtorRva);

    memset(reqBuf, 0, sizeof(reqBuf));
    void* tmp[6] = {}; // moved into req by assemble

    bool ok = true;
    ok &= MakeQQString(tmp[0], gp.pcBody.data(), gp.pcBody.size(), mkstr);
    ok &= MakeQQString(tmp[1], gp.index.data(), gp.index.size(), mkstr);
    ok &= MakeQQString(tmp[2], gp.pbReserve.data(), gp.pbReserve.size(), mkstr);
    ok &= MakeQQString(tmp[3], gp.name.data(), gp.name.size(), mkstr);
    ok &= MakeQQString(tmp[4], gp.wishing.data(), gp.wishing.size(), mkstr);
    ok &= MakeQQString(tmp[5], gp.peerUid.data(), gp.peerUid.size(), mkstr);
    if (!ok) {
        reqBufUsed = false;
        SendEvent("{\"event\":\"grab_result\",\"error\":\"string alloc failed\"}");
        return;
    }

    assemble(reqBuf, tmp[0], tmp[1], tmp[2], tmp[3], tmp[4],
             gp.recvUin, tmp[5], gp.recvType, gp.msgSeq);

    // req shared_ptr: {ptr=reqBuf, ctrl=fake} - fake ctrl refcount never hits 0.
    void* reqSp[2] = { (void*)reqBuf, g_ctrl };
    // callback shared_ptr: QQ's own members, refcount +1 (never released on
    // purpose; agent lives as long as the process).
    void* cbSp[2] = { cbPtr, cbCtrl };
    InterlockedIncrement((volatile LONG*)((uint8_t*)cbCtrl + 8));

    typedef void* (__fastcall* FnGrabEntry)(void* self, void** reqSp, void** cbSp);
    SendEvent("{\"event\":\"log\",\"msg\":\"calling GrabRedBagEntry via vtable+0x810\"}");
    ((FnGrabEntry)grabEntry)(inst, reqSp, cbSp);
    // NB: do NOT run rdtor(reqBuf) - buffer is static and the async task may
    // still reference QQ-internal copies; request dtor is owned by the task.
    SendEvent("{\"event\":\"log\",\"msg\":\"grab entry returned\"}");
}

#if 0  // original implementation kept for the replay rework
static void RunGrabOld(const GrabParams& gp) {
    void* inst = g_inst;
    if (!inst) { SendEvent("{\"event\":\"grab_result\",\"error\":\"instance not captured yet\"}"); return; }

    FnAssemble assemble = (FnAssemble)(g_base + kAssembleRva);
    FnStrFromPend mkstr = (FnStrFromPend)(g_base + kStrFromPendRva);
    FnStrDtor    sdtor  = (FnStrDtor)(g_base + kStrDtorRva);
    FnReqDtor    rdtor  = (FnReqDtor)(g_base + kReqDtorRva);

    alignas(16) uint8_t req[kReqSize];
    memset(req, 0, sizeof(req));
    void* tmp[6] = {}; // moved into req by assemble

    bool ok = true;
    ok &= MakeQQString(tmp[0], gp.pcBody.data(), gp.pcBody.size(), mkstr);
    ok &= MakeQQString(tmp[1], gp.index.data(), gp.index.size(), mkstr);
    ok &= MakeQQString(tmp[2], gp.pbReserve.data(), gp.pbReserve.size(), mkstr);
    ok &= MakeQQString(tmp[3], gp.name.data(), gp.name.size(), mkstr);
    ok &= MakeQQString(tmp[4], gp.wishing.data(), gp.wishing.size(), mkstr);
    ok &= MakeQQString(tmp[5], gp.peerUid.data(), gp.peerUid.size(), mkstr);
    if (!ok) { SendEvent("{\"event\":\"grab_result\",\"error\":\"string alloc failed\"}"); return; }

    // assemble moves tmp strings into req; after this tmp[] are reset by QQ code.
    assemble(req, tmp[0], tmp[1], tmp[2], tmp[3], tmp[4],
             gp.recvUin, tmp[5], gp.recvType, gp.msgSeq);

    // Fake shared_ptr: {_Ptr = ctrl+0x18, _Ctrl = ctrl} matching MSVC layout.
    void* cbSp[2] = { g_ctrl + 0x18, g_ctrl };

    void* vt = *(void**)inst;
    FnGrab grab = *(FnGrab*)((uint8_t*)vt + kGrabVtSlot);
    if (!grab) { SendEvent("{\"event\":\"grab_result\",\"error\":\"null grab fn\"}"); return; }

    SendEvent("{\"event\":\"log\",\"msg\":\"calling grabRedBag\"}");
    grab(inst, req, cbSp);
    rdtor(req);
    SendEvent("{\"event\":\"log\",\"msg\":\"grab call returned\"}");
}
#endif


// ---- assemble capture hook -----------------------------------------------------
// Inline hook on assemble (12B stolen prologue): every grabRedBag call (incl.
// QQ's own path when the user clicks a red packet) funnels through here, so a
// single manual grab calibrates our template with exact field values.
static uint8_t g_assembleTramp[32];   // stolen bytes + jmp back
typedef void* (__fastcall* FnAssembleTramp)(void* dest, void* pcBody, void* index,
                                            void* pbReserve, void* name, void* wishing,
                                            uint64_t recvUin, void* peerUid,
                                            uint32_t recvType, uint64_t msgSeq);
struct CapturedGrab {
    std::string pcBody, index, pbReserve, name, wishing, peerUid;
    uint64_t recvUin = 0, msgSeq = 0;
    uint32_t recvType = 0;
    bool valid = false;
};
static CapturedGrab g_captured;

static void* __fastcall HookAssemble(void* dest, void* a1, void* a2,
                                     void* a3, void* a4, void* a5,
                                     void* a6, void* a7, void* a8,
                                     void* a9) {
    // __fastcall: dest=rcx, a1=rdx, a2=r8, a3=r9, a4..a9 = 栈参
    // 对每个指针槽：按 QQ inline string 读 24B（ptr/len/cap）+ 原始 hex
    auto dumpSlot = [](void* p) -> std::string {
        if (!p) return "<null>";
        std::string s = ReadQQString(p);
        uint8_t raw[24];
        memcpy(raw, p, 24);
        char hex[64];
        for (int i = 0; i < 24; ++i) {
            hex[2*i]   = "0123456789abcdef"[(raw[i] >> 4) & 0xF];
            hex[2*i+1] = "0123456789abcdef"[raw[i] & 0xF];
        }
        hex[48] = 0;
        return "{\"str\":\"" + EscapeJson(s) + "\",\"raw\":\"" + std::string(hex) + "\"}";
    };
    char numbuf[2][32];
    snprintf(numbuf[0], 32, "%llu", (unsigned long long)(uintptr_t)a4);
    snprintf(numbuf[1], 32, "%llu", (unsigned long long)(uintptr_t)a5);
    std::string line = "{\"event\":\"captured2\""
                       ",\"a1\":" + dumpSlot(a1) +
                       ",\"a2\":" + dumpSlot(a2) +
                       ",\"a3\":" + dumpSlot(a3) +
                       ",\"a4\":" + std::string(numbuf[0]) +
                       ",\"a5\":" + std::string(numbuf[1]) +
                       ",\"a6\":" + dumpSlot(a6) +
                       ",\"a7\":" + dumpSlot(a7) +
                       ",\"a8\":" + dumpSlot(a8) +
                       ",\"a9\":" + dumpSlot(a9) + "}";
    EnterCriticalSection(&g_cs);
    g_captured.valid = true;
    LeaveCriticalSection(&g_cs);
    SendEventString(line);
    auto tramp = reinterpret_cast<FnAssembleTramp>((void*)g_assembleTramp);
    return reinterpret_cast<void*(*)(void*, void*, void*, void*, void*, void*, void*, void*, void*, void*)>(g_assembleTramp)(dest, a1, a2, a3, a4, a5, a6, a7, a8, a9);
}



static bool HookAssembleEntry() {
    uint8_t* entry = (uint8_t*)(g_base + kAssembleRva);
    // verify expected prologue: 8x push + 48 83 EC 28 (sub rsp,0x28)
    static const uint8_t want[12] = {0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,
                                     0x56,0x57,0x55,0x53};
    if (memcmp(entry, want, 12) != 0) {
        Dbg("[grab-agent] assemble prologue mismatch\n");
        return false;
    }
    // build trampoline: stolen 12B + jmp rel32 back to entry+12
    memcpy(g_assembleTramp, entry, kAsmStolenLen);
    g_assembleTramp[kAsmStolenLen] = 0xE9;
    int32_t rel = (int32_t)((entry + kAsmStolenLen) - (g_assembleTramp + kAsmStolenLen + 5));
    memcpy(g_assembleTramp + kAsmStolenLen + 1, &rel, 4);
    DWORD old = 0;
    if (!VirtualProtect(g_assembleTramp, sizeof(g_assembleTramp), PAGE_EXECUTE_READWRITE, &old))
        return false;
    if (!VirtualProtect(entry, kAsmStolenLen + 8, PAGE_EXECUTE_READWRITE, &old))
        return false;
    uint8_t patch[12];
    patch[0] = 0x48, patch[1] = 0xB8;              // mov rax, imm64
    *(void**)(patch + 2) = (void*)&HookAssemble;
    patch[10] = 0xFF, patch[11] = 0xE0;            // jmp rax
    memcpy(entry, patch, kAsmStolenLen);
    VirtualProtect(entry, kAsmStolenLen + 8, old, &old);
    FlushInstructionCache(GetCurrentProcess(), entry, kAsmStolenLen);
    g_asmHooked = true;
    SendEvent("{\"event\":\"log\",\"msg\":\"assemble hook installed\"}");
    return true;
}

// ---- minimal JSON field extraction (no deps) ---------------------------------
// Values are simple flat objects: {"op":"grab","pcBody":"...","index":"...",...}
static bool JsonGetString(const char* json, const char* key, std::string& out) {
    char pat[64];
    _snprintf_s(pat, sizeof(pat), _TRUNCATE, "\"%s\":\"", key);
    const char* p = strstr(json, pat);
    if (!p) return false;
    p += strlen(pat);
    while (*p) {
        if (*p == '\\' && p[1]) { out += p[1]; p += 2; continue; }
        if (*p == '"') break;
        out += *p++;
    }
    return true;
}

static bool JsonGetU64(const char* json, const char* key, uint64_t& out) {
    char pat[48];
    _snprintf_s(pat, sizeof(pat), _TRUNCATE, "\"%s\":", key);
    const char* p = strstr(json, pat);
    if (!p) return false;
    out = _strtoui64(p + strlen(pat), nullptr, 10);
    return true;
}

// ---- pipe server ----------------------------------------------------------------
static bool ReadFrame(HANDLE p, std::string& out) {
    uint32_t n = 0;
    DWORD r = 0;
    if (!ReadFile(p, &n, 4, &r, nullptr) || r != 4) return false;
    if (n == 0 || n > (1u << 20)) return false;
    out.resize(n);
    char* dst = &out[0];
    size_t got = 0;
    while (got < n) {
        if (!ReadFile(p, dst + got, (DWORD)(n - got), &r, nullptr) || !r) return false;
        got += r;
    }
    return true;
}

static void HandleCommand(const std::string& cmd) {
    EnqueueEvent(std::string("{\"event\":\"log\",\"msg\":\"diag: handle cmd\"}"));
    if (cmd.find("status") != std::string::npos) {
        char line[192];
        _snprintf_s(line, sizeof(line), _TRUNCATE,
            "{\"event\":\"status\",\"wrapper\":\"%p\",\"inst\":\"%llu\",\"hooked\":%s,\"asm_hook\":%s,\"captured\":%s}",
            (void*)g_base, (unsigned long long)(uintptr_t)g_inst,
            g_origUnwrap ? "true" : "false",
            g_asmHooked ? "true" : "false",
            g_captured.valid ? "true" : "false");
        SendEvent(line);
        if (g_captured.valid) {
            char cap[320];
            _snprintf_s(cap, sizeof(cap), _TRUNCATE,
                "{\"event\":\"captured_info\",\"msgSeq\":%llu,\"recvUin\":%llu,\"recvType\":%u,\"pcBodyLen\":%zu,\"peerUidLen\":%zu}",
                (unsigned long long)g_captured.msgSeq,
                (unsigned long long)g_captured.recvUin,
                g_captured.recvType,
                g_captured.pcBody.size(), g_captured.peerUid.size());
            SendEvent(cap);
        }
        return;
    }
    if (cmd.find("grab") != std::string::npos) {
        GrabParams gp;
        bool have = false;
        have |= JsonGetString(cmd.c_str(), "pcBody", gp.pcBody);
        have |= JsonGetString(cmd.c_str(), "index", gp.index);
        have |= JsonGetString(cmd.c_str(), "pbReserve", gp.pbReserve);
        have |= JsonGetString(cmd.c_str(), "name", gp.name);
        have |= JsonGetString(cmd.c_str(), "wishing", gp.wishing);
        have |= JsonGetString(cmd.c_str(), "peerUid", gp.peerUid);
        uint64_t v = 0;
        if (JsonGetU64(cmd.c_str(), "recvUin", v)) { gp.recvUin = v; have = true; }
        if (JsonGetU64(cmd.c_str(), "msgSeq", v)) { gp.msgSeq = v; have = true; }
        if (JsonGetU64(cmd.c_str(), "recvType", v)) { gp.recvType = (uint32_t)v; have = true; }
        // 未提供的字段回退到捕获模板（用户手点一次后自动校准）
        EnterCriticalSection(&g_cs);
        CapturedGrab snap = g_captured;
        LeaveCriticalSection(&g_cs);
        if (snap.valid) {
            if (gp.pcBody.empty()) gp.pcBody = snap.pcBody;
            if (gp.index.empty()) gp.index = snap.index;
            if (gp.pbReserve.empty()) gp.pbReserve = snap.pbReserve;
            if (gp.name.empty()) gp.name = snap.name;
            if (gp.wishing.empty()) gp.wishing = snap.wishing;
            if (gp.peerUid.empty()) gp.peerUid = snap.peerUid;
            if (!gp.recvUin) gp.recvUin = snap.recvUin;
            if (!gp.msgSeq) gp.msgSeq = snap.msgSeq;
            if (!gp.recvType) gp.recvType = snap.recvType;
        }
        RunGrab(gp);
        return;
    }
    SendEvent("{\"event\":\"log\",\"msg\":\"unknown op\"}");
}

static DWORD WINAPI EvPipeThread(LPVOID) {
    for (;;) {
        HANDLE ev = CreateNamedPipeA(
            "\\\\.\\pipe\\elaina_grab_agent_v2_ev",
            PIPE_ACCESS_OUTBOUND, PIPE_TYPE_BYTE | PIPE_WAIT,
            1, 1 << 16, 1 << 16, 0, nullptr);
        if (ev == INVALID_HANDLE_VALUE) { Sleep(2000); continue; }
        if (!ConnectNamedPipe(ev, nullptr) && GetLastError() != ERROR_PIPE_CONNECTED) {
            CloseHandle(ev); continue;
        }
        TraceFile("ev pipe: client connected");
        EnterCriticalSection(&g_cs);
        g_evPipe = ev;
        LeaveCriticalSection(&g_cs);
        // hold until cmd side signals disconnect
        while (true) {
            EnterCriticalSection(&g_cs);
            HANDLE cmd = g_pipe;
            LeaveCriticalSection(&g_cs);
            if (cmd == INVALID_HANDLE_VALUE) break;
            Sleep(200);
        }
        EnterCriticalSection(&g_cs);
        g_evPipe = INVALID_HANDLE_VALUE;
        LeaveCriticalSection(&g_cs);
        DisconnectNamedPipe(ev);
        CloseHandle(ev);
    }
    return 0;
}

static DWORD WINAPI PipeThread(LPVOID) {
    for (;;) {
        HANDLE pipe = CreateNamedPipeA(
            "\\\\.\\pipe\\elaina_grab_agent_v2",
            PIPE_ACCESS_INBOUND, PIPE_TYPE_BYTE | PIPE_WAIT,
            1, 1 << 16, 1 << 16, 0, nullptr);
        if (pipe == INVALID_HANDLE_VALUE) { Sleep(2000); continue; }
        if (!ConnectNamedPipe(pipe, nullptr) && GetLastError() != ERROR_PIPE_CONNECTED) {
            CloseHandle(pipe); continue;
        }
        // publish active client pipe for EvWriterThread
        EnterCriticalSection(&g_cs);
        g_pipe = pipe;
        LeaveCriticalSection(&g_cs);
        EnqueueEvent(std::string("{\"event\":\"log\",\"msg\":\"diag: client connected\"}"));
        TraceFile(std::string("pipe: client connected, pipe=") + std::to_string((uintptr_t)pipe));
        std::string cmd;
        while (ReadFrame(pipe, cmd)) {
            EnqueueEvent(std::string("{\"event\":\"log\",\"msg\":\"diag: frame len=") + std::to_string(cmd.size()) + "\"}");
            TraceFile("pipe: frame recv len=" + std::to_string(cmd.size()));
            HandleCommand(cmd);
            cmd.clear();
        }
        EnterCriticalSection(&g_cs);
        g_pipe = INVALID_HANDLE_VALUE;
        LeaveCriticalSection(&g_cs);
        DisconnectNamedPipe(pipe);
        CloseHandle(pipe);
    }
    return 0;
}

// ---- entry -----------------------------------------------------------------------
static DWORD WINAPI InitThread(LPVOID) {
    InitializeCriticalSection(&g_cs);
    TraceFile("init thread: cs ready, starting ev writer");
    CreateThread(nullptr, 0, EvWriterThread, nullptr, 0, nullptr);
    // locate wrapper.node
    for (;;) {
        HMODULE m = GetModuleHandleA("wrapper.node");
        if (m) { g_wrapper = m; break; }
        Sleep(500);
    }
    g_base = (uintptr_t)g_wrapper;
    TraceFile("init: wrapper base found");
    char line[160];
    _snprintf_s(line, sizeof(line), _TRUNCATE,
                "{\"event\":\"log\",\"msg\":\"wrapper base=%llu\"}",
                (unsigned long long)g_base);
    SendEvent(line);

    InitCtrl();
    CreateThread(nullptr, 0, PipeThread, nullptr, 0, nullptr);
    CreateThread(nullptr, 0, EvPipeThread, nullptr, 0, nullptr);
    // retry hook until slot is populated (may load after us)
    for (int i = 0; i < 120; ++i) {
        void* v = *(void**)(g_base + kUnwrapSlotRva);
        if (v) { if (HookUnwrapSlot()) break; }
        Sleep(1000);
    }
    HookAssembleEntry();
    return 0;
}

BOOL APIENTRY DllMain(HMODULE hMod, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hMod);
        TraceFile("dll attached");
        CreateThread(nullptr, 0, InitThread, nullptr, 0, nullptr);
    }
    return TRUE;
}
