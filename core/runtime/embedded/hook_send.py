"""PbSendMsg / 撤回等发送侧 protobuf 编码（字段号与 SnowLuma encoder 对齐）。

字段表（``index.mjs`` ``protobuf_encode_*`` 系列逐一核对）::

    SendMessageRequest   f1=routingHead f2=contentHead f3=messageBody
                         f4=clientSequence f5=random f6=syncCookie
                         f7=via f8=dataStatist f9=ctrl(MessageControl)
                         f10=multiSendSeq
    RoutingHead          f1=c2c(RoutingC2C) f2=grp(RoutingGroup)
                         f3=grpTmp(RoutingGrpTmp) f4=trans0x211(RoutingTrans0x211)
    RoutingC2C           f1=uin f2=uid
    RoutingGroup         f1=groupCode(u64)
    RoutingGrpTmp        f1=groupUin(u64) f2=toUid
    RoutingTrans0x211    f1=toUin f2=ccCmd f3=uid
    SendContentHead      f1=type f2=subType f3=c2cCmd
    MessageControl       f1=msgFlag
    MessageBody          f1=richText f2=msgContent
    RichText             f2=elems[](Elem)   (attr f1/attr2 忽略)
    Elem                 f1=text f2=face f6=marketFace f8=customFace
                         f12=richMsg f13=groupFile f45=srcMsg f51=lightApp
                         f53=commonElem
    TextElem             f1=str f3=attr6Buf f12=pbReserve(MentionExtraSend)
    MentionExtraSend     f3=type f4=uin f5=field5 f9=uid
    FaceElem             f1=index
    QSmallFaceExtra      f1=faceId f2=preview f3=preview2
    QFaceExtra           f1=packId f2=stickerId f3=qsid f4=sourceType
                         f5=stickerType f7=text f8=randomType
    LightAppElem         f1=data f2=msgResid
    RichMsg              f1=template1 f2=serviceId
    CommonElem           f1=serviceType f2=pbElem f3=businessType
    SrcMsg               f1=origSeqs(rep varint) f2=senderUin(u64) f3=time
    SendMessageResponse  f1=result f2=errMsg f3=timestamp1
                         f5=groupSequence f7=privateSequence
    GroupRecallRequest   f1=type f2=groupUin(u64) f4=info f5=settings
    GroupRecallInfo      f1=sequence f2=random f3=field3
    GroupRecallSettings  f1=field1
    C2CRecallRequest     f1=type f4=info f5=settings f6=field6(bool)
    C2CRecallInfo        f1=clientSequence f2=random f3=messageId(u64)
                         f4=timestamp f5=field5 f6=messageSequence
    C2CRecallSettings    f1=field1(bool) f2=field2(bool)
"""

from __future__ import annotations

import struct
import zlib
from typing import Any

SEND_MSG_CMD = 'MessageSvc.PbSendMsg'
GROUP_RECALL_CMD = 'trpc.msg.msg_svc.MsgService.SsoGroupRecallMsg'
C2C_RECALL_CMD = 'trpc.msg.msg_svc.MsgService.SsoC2CRecallMsg'

# ---------------------------------------------------------------------------

# 简易选择表情分类（与 sysFaceStore.classify 近似：小表情 0-104 频段之外的常见大表情）
_SUPER_FACE_IDS = frozenset(range(200, 220))


def _varint(value: int) -> bytes:
    if value < 0:
        value &= (1 << 64) - 1
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _tag(number: int, wire: int) -> bytes:
    return _varint((number << 3) | wire)


def vfield(number: int, value: int) -> bytes:
    """varint 字段（bool/int32/int64 通用，非零才写，与 proto3 语义一致）。"""
    if not value:
        return b''
    return _tag(number, 0) + _varint(value)


def bfield(number: int, data: bytes, *, always: bool = False) -> bytes:
    """bytes/子消息字段（空可跳过，除非 always）。"""
    if not data and not always:
        return b''
    return _tag(number, 2) + _varint(len(data)) + data


def _deflated_payload(content: str) -> bytes:
    compressed = zlib.compress(content.encode('utf-8'), 9)
    return b'\x01' + compressed


# -- 基础子结构 ---------------------------------------------------------------


def encode_text_elem(text: str, mention: bytes = b'') -> bytes:
    body = bfield(1, text.encode('utf-8'))
    body += bfield(12, mention)
    return bfield(1, body)


def encode_mention_extra(m_type: int, uin: int, uid: str) -> bytes:
    body = vfield(3, m_type) + vfield(4, uin) + bfield(9, uid.encode('utf-8'))
    return body


def encode_at_elem(target_uin: int, uid: str = '', display: str = '') -> bytes:
    mention_all = target_uin == 0
    m_type = 1 if mention_all else 2
    extra = encode_mention_extra(m_type, 0 if mention_all else target_uin,
                                 'all' if mention_all else uid)
    text = '@全体成员 ' if mention_all else f'@{display or target_uin} '
    return encode_text_elem(text, extra)


def encode_face_elem(face_id: int) -> bytes:
    if face_id in _SUPER_FACE_IDS:
        extra = (vfield(3, face_id) + vfield(4, 1) + vfield(8, 1))
        return bfield(53, vfield(1, 37) + bfield(2, extra) + vfield(3, 1))
    if 0 <= face_id < 300:
        extra = vfield(1, face_id)
        return bfield(53, vfield(1, 33) + bfield(2, extra) + vfield(3, 1))
    return bfield(2, vfield(1, face_id))


def encode_reply_elem(src_seq: int, sender_uin: int = 0, time_: int = 0) -> bytes:
    body = bfield(1, _varint(src_seq & 0xFFFFFFFF), always=True)
    body += vfield(2, sender_uin) + vfield(3, time_)
    return bfield(45, body)


def encode_json_elem(data: str) -> bytes:
    return bfield(51, bfield(1, _deflated_payload(data), always=True))


def encode_xml_elem(data: str, service_id: int = 35) -> bytes:
    body = bfield(1, _deflated_payload(data), always=True) + vfield(2, service_id)
    return bfield(12, body)


def encode_send_message_request(*, routing: bytes, content_head: bytes,
                                rich_elems: list[bytes] | None = None,
                                msg_content: bytes = b'',
                                client_sequence: int = 0, random: int = 0) -> bytes:
    rich = b''.join(bfield(2, elem) for elem in (rich_elems or []))
    message_body = bfield(1, rich) + bfield(2, msg_content)
    body = (
        bfield(1, routing)
        + bfield(2, content_head)
        + bfield(3, message_body)
        + vfield(4, client_sequence)
        + vfield(5, random)
    )
    return body


def routing_group(group_code: int) -> bytes:
    return bfield(2, vfield(1, int(group_code)), always=True)


def routing_c2c(uin: int, uid: str = '') -> bytes:
    body = vfield(1, int(uin)) + bfield(2, uid.encode('utf-8'))
    return bfield(1, body, always=True)


def routing_grp_tmp(group_uin: int, to_uid: str) -> bytes:
    body = vfield(1, int(group_uin)) + bfield(2, to_uid.encode('utf-8'))
    return bfield(3, body, always=True)


def content_head(type_: int = 1, sub_type: int = 0, c2c_cmd: int = 0) -> bytes:
    return vfield(1, type_) + vfield(2, sub_type) + vfield(3, c2c_cmd)


# -- 撤回 ---------------------------------------------------------------------


def encode_group_recall_request(group_uin: int, sequence: int) -> bytes:
    info = vfield(1, sequence)
    settings = b''  # settings.field1 = 0（proto3 省略）
    body = (
        vfield(1, 1)
        + vfield(2, int(group_uin))
        + bfield(4, info, always=True)
        + bfield(5, settings)
    )
    return body


def encode_c2c_recall_request(target_uid: str, client_seq: int, msg_seq: int,
                              random: int, timestamp: int) -> bytes:
    info = (
        vfield(1, client_seq)
        + vfield(2, random)
        + vfield(3, (16777216 << 32) + random)
        + vfield(4, timestamp)
        + vfield(6, msg_seq)
    )
    settings = vfield(1, 0) + vfield(2, 0)
    return vfield(1, 1) + bfield(4, info, always=True) + bfield(5, settings, always=True)


# -- 响应解码 ------------------------------------------------------------------


def parse_send_response(body: bytes) -> dict[str, Any]:
    """SendMessageResponse → {result, err_msg, timestamp, group_seq, private_seq}。"""
    from core.runtime.embedded.hook_msgpush import pb_bytes, pb_int, pb_str

    return {
        'result': pb_int(body, 1),
        'err_msg': pb_str(body, 2),
        'timestamp': pb_int(body, 3),
        'group_seq': pb_int(body, 5),
        'private_seq': pb_int(body, 7),
    }


def rand32(base: int = 0) -> int:
    import random
    return random.getrandbits(31)
