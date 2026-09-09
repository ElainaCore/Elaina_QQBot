// ---- assemble capture hook ---------------------------------------------------
// Hook 0x101ACD0 (assemble UGrabRedBagReq) so a single manual grab by the user
// teaches us the exact pcBody/index/pbReserve/name/wishing/peerUid/recvType/
// msgSeq QQ produces. Captured template is stored and reused by op=grab.
#include <intrin.h>

typedef void* (__fastcall* FnAssembleReal)(void* dest, void* pcBody, void* index,
                                           void* pbReserve, void* name, void* wishing,
                                           uint64_t recvUin, void* peerUid,
                                           uint32_t recvType, uint64_t msgSeq);

static FnAssembleReal g_realAssemble = nullptr;
static uint8_t* g_assembleEntry = nullptr;
static uint8_t g_assembleOrig[16];
static volatile LONG g_captureSeq = 0;

struct CapturedGrab {
    std::string pcBody, index, pbReserve, name, wishing, peerUid;
    uint64_t recvUin = 0, msgSeq = 0;
    uint32_t recvType = 0;
    bool valid = false;
};
static CapturedGrab g_captured;
static CRITICAL_SECTION g_capcs;

static void CopyQQString(void* s, std::string& out) { out = ReadQQString(s); }

// Trampoline: log params, then run original bytes + jump back.
static void* __fastcall HookAssemble(void* dest, void* pcBody, void* index,
                                     void* pbReserve, void* name, void* wishing,
                                     uint64_t recvUin, void* peerUid,
                                     uint32_t recvType, uint64_t msgSeq) {
    // capture before executing original (strings are moved-into dest)
    EnterCriticalSection(&g_capcs);
    if (InterlockedIncrement(&g_captureSeq) > 0) {
        CapturedGrab c;
        CopyQQString(pcBody, c.pcBody);
        CopyQQString(index, c.index);
        CopyQQString(pbReserve, c.pbReserve);
        CopyQQString(name, c.name);
        CopyQQString(wishing, c.wishing);
        CopyQQString(peerUid, c.peerUid);
        c.recvUin = recvUin;
        c.recvType = recvType;
        c.msgSeq = msgSeq;
        c.valid = true;
        g_captured = c;
        char line[128];
        _snprintf_s(line, sizeof(line), _TRUNCATE,
                    "{\"event\":\"captured\",\"recvType\":%u,\"recvUin\":%llu}",
                    recvType, (unsigned long long)recvUin);
        SendEvent(line);
    }
    LeaveCriticalSection(&g_capcs);
    // execute stolen prologue then jump back
    void* ret;
    void** args = (void**)&dest; // not used; we tail-jump via asm below
    (void)args;
    // We cannot easily continue the original from C with 10 args; instead we
    // call a copied-prologue trampoline built at hook time.
    return AssembleTrampoline(dest, pcBody, index, pbReserve, name, wishing,
                              recvUin, peerUid, recvType, msgSeq);
}
