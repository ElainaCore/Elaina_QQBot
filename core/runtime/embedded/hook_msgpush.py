"""MsgPush 原始包 protobuf 解码。

字段号全部与 SnowLuma 桥接运行时（``index.mjs`` protobuf_decode_* 系列函数）
逐一对齐，不凭记忆推断：

- ``PushMsg``            顶层: f1=message(PushMsgBody), f3=status(u64)
- ``PushMsgBody``        f1=ResponseHead, f2=ContentHead, f3=MessageBody
- ``ContentHead``        f1=msgType, f2=subType, f3=c2cCmd, f4=msgId,
                         f5=sequence, f6=timestamp, f11=ntMsgSeq, f12=newId
- ``ResponseHead``       f1=fromUin, f2=fromUid, f5=toUin, f8=grp(ResponseGrp)
- ``ResponseGrp``        f1=groupUin, f2=memberName, f4=memberCard, f7=groupName
- ``MessageBody``        f1=RichText, f2=msgContent
- ``RichText``           f2=elems[](Elem), f3=notOnlineFile, f4=ptt
- ``Elem``               f1=text f2=face f4=notOnlineImage f5=transElem
                         f6=marketFace f8=customFace f12=richMsg f13=groupFile
                         f16=extraInfo f19=videoFile f37=generalFlags
                         f45=srcMsg f51=lightApp f53=commonElem
- ``TextElem``           f1=str f2=link f3=attr6Buf f4=attr7Buf f11=buf
                         f12=pbReserve(MentionExtra)
- ``MentionExtra``       f3=type f4=uin f5=field5 f9=uid
- ``FaceElem``           f1=index
- ``NotOnlineImage``     f1=filePath f2=fileLen f7=picMd5 f8=picHeight
                         f9=picWidth f10=resId f14=bigUrl f15=origUrl f29=pbRes
- ``CustomFace``         f2=filePath f13=md5 f16=origUrl f22=width f23=height
                         f25=size
- ``Ptt``                f1=fileType f2=fileId(u64) f3=fileUuid(bytes)
                         f4=fileMd5 f5=fileName f6=fileSize f10=groupFileKey
                         f14=fileKey f19=time f29=format
- ``NotOnlineFile``      f1=fileType f3=fileUuid f4=fileMd5 f5=fileName
                         f6=fileSize f9=subcmd f57=fileHash
- ``VideoFile``          f1=fileUuid f2=fileMd5 f3=fileName f4=fileFormat
                         f5=fileTime f6=fileSize f7=thumbWidth f8=thumbHeight
- ``GroupFileElem``      f1=filename f2=fileSize f3=fileId
- ``MarketFace``         f4=faceName f7=faceId f8=tabId f10=key
- ``RichMsg``            f1=template1 f2=serviceId
- ``LightAppElem``       f1=data f2=msgResid
- ``CommonElem``         f1=serviceType f2=pbElem f3=businessType
- ``SrcMsg``             f1=origSeqs(rep varint) f2=senderUin f3=time
                         f5=elemsRaw
- ``FileExtra``(msgContent) f1=file(NotOnlineFile)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field as dc_field
from typing import Any

log = logging.getLogger('ElainaQQ.embedded_qq.msgpush')

# ---------------------------------------------------------------------------
# protobuf wire format
# ---------------------------------------------------------------------------

_MAX_DEPTH = 64


def read_varint(data: bytes, offset: int, end: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        if offset >= end:
            raise ValueError('varint 越界')
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
        if shift >= 70:
            raise ValueError('varint 过长')


def iter_fields(data: bytes, offset: int = 0, end: int | None = None,
                depth: int = 0) -> list[tuple[int, int, bytes]]:
    """返回 [(field_number, wire_type, raw_value)]。

    wire 0/1/2/5 常规处理；wire 3/4 (start/end group) 递归跳过，
    兼容个别包体里的 group 编码而不抛错。
    """
    out: list[tuple[int, int, bytes]] = []
    end = len(data) if end is None else end
    while offset < end:
        tag, offset = read_varint(data, offset, end)
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError('protobuf 字段号 0 非法')
        if wire == 0:
            value, offset = read_varint(data, offset, end)
            out.append((number, 0, value.to_bytes((value.bit_length() + 7) // 8 or 1, 'little')))
        elif wire == 1:
            if offset + 8 > end:
                raise ValueError('fixed64 越界')
            out.append((number, 1, data[offset:offset + 8]))
            offset += 8
        elif wire == 2:
            length, offset = read_varint(data, offset, end)
            if offset + length > end:
                raise ValueError('长度越界')
            out.append((number, 2, data[offset:offset + length]))
            offset += length
        elif wire == 5:
            if offset + 4 > end:
                raise ValueError('fixed32 越界')
            out.append((number, 5, data[offset:offset + 4]))
            offset += 4
        elif wire == 3:
            if depth >= _MAX_DEPTH:
                raise ValueError('group 嵌套过深')
            inner_end = _skip_group(data, offset, end, number, depth + 1)
            inner = iter_fields(data, offset, inner_end, depth + 1)
            out.append((number, 3, b''))
            out.extend(inner)
            offset = inner_end
        elif wire == 4:
            raise ValueError('不配对的 end-group')
        else:
            raise ValueError(f'不支持的 wire type {wire}')
    return out


def _skip_group(data: bytes, offset: int, end: int, field_number: int, depth: int) -> int:
    """跳过 group 内容，返回 end-group 之后的偏移。"""
    while offset < end:
        tag, offset = read_varint(data, offset, end)
        number, wire = tag >> 3, tag & 7
        if wire == 4:
            if number != field_number:
                raise ValueError('group 结束标签不匹配')
            return offset
        if wire == 0:
            _, offset = read_varint(data, offset, end)
        elif wire == 1:
            offset += 8
        elif wire == 2:
            length, offset = read_varint(data, offset, end)
            offset += length
        elif wire == 5:
            offset += 4
        elif wire == 3:
            offset = _skip_group(data, offset, end, number, depth + 1)
        else:
            raise ValueError(f'group 内不支持的 wire type {wire}')
        if offset > end:
            raise ValueError('group 越界')
    raise ValueError('group 未闭合')


def pb_int(data: bytes, number: int, default: int = 0) -> int:
    for num, wire, raw in iter_fields(data):
        if num == number and wire in (0, 1, 5):
            return int.from_bytes(raw, 'little')
    return default


def pb_bytes(data: bytes, number: int, default: bytes = b'') -> bytes:
    for num, wire, raw in iter_fields(data):
        if num == number and wire == 2:
            return raw
    return default


def pb_str(data: bytes, number: int, default: str = '') -> str:
    raw = pb_bytes(data, number)
    return raw.decode('utf-8', 'replace') if raw else default


def pb_list(data: bytes, number: int) -> list[bytes]:
    return [raw for num, wire, raw in iter_fields(data) if num == number and wire == 2]


def pb_int_list(data: bytes, number: int) -> list[int]:
    return [int.from_bytes(raw, 'little') for num, wire, raw in iter_fields(data)
            if num == number and wire == 0]


# ---------------------------------------------------------------------------
# PushMsg 顶层
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class MsgContext:
    """一条推送消息的解析上下文（字段与 SnowLuma buildContext 对齐）。"""

    msg_type: int = 0
    sub_type: int = 0
    c2c_cmd: int = 0
    msg_id: int = 0          # u64 原值；int32 用法需 & 0x7FFFFFFF
    sequence: int = 0
    nt_msg_seq: int = 0
    timestamp: int = 0
    from_uin: int = 0
    from_uid: str = ''
    to_uin: int = 0
    self_uin: int = 0
    group_uin: int = 0
    member_name: str = ''
    member_card: str = ''
    group_name: str = ''
    raw_pb: bytes = dc_field(default=b'', repr=False)
    body: bytes = dc_field(default=b'', repr=False)

    @property
    def is_group(self) -> bool:
        return self.msg_type == 82

    @property
    def peer_uin(self) -> int:
        """私聊会话对端（自发回显时为接收方）。"""
        if 0 < self.from_uin == self.self_uin:
            return self.to_uin
        return self.from_uin


def parse_push(body: bytes, self_uin: int = 0) -> list[MsgContext]:
    """解析 ``trpc.msg.olpush.OlPushService.MsgPush`` 包体。

    顶层为单数 ``message``（field 1），实践中重复出现时逐条解析。
    """
    contexts: list[MsgContext] = []
    for message in pb_list(body, 1) or []:
        try:
            ctx = _parse_message(message, self_uin)
        except (ValueError, IndexError) as exc:
            log.debug('MsgPush 单条消息解析失败: %s', exc)
            continue
        if ctx is not None:
            contexts.append(ctx)
    return contexts


def _parse_message(message: bytes, self_uin: int) -> MsgContext | None:
    response_head = pb_bytes(message, 1)
    content_head = pb_bytes(message, 2)
    message_body = pb_bytes(message, 3)
    if not content_head:
        return None
    ctx = MsgContext(
        msg_type=pb_int(content_head, 1),
        sub_type=pb_int(content_head, 2),
        c2c_cmd=pb_int(content_head, 3),
        msg_id=pb_int(content_head, 4),
        sequence=pb_int(content_head, 5),
        timestamp=pb_int(content_head, 6),
        nt_msg_seq=pb_int(content_head, 11),
        self_uin=self_uin,
        raw_pb=message,
    )
    ctx.from_uin = pb_int(response_head, 1)
    ctx.from_uid = pb_str(response_head, 2)
    ctx.to_uin = pb_int(response_head, 5)
    grp = pb_bytes(response_head, 8)  # ResponseHead.grp = field 8
    if grp:
        ctx.group_uin = pb_int(grp, 1)
        ctx.member_name = pb_str(grp, 2)
        ctx.member_card = pb_str(grp, 4)   # memberCard = field 4
        ctx.group_name = pb_str(grp, 7)    # groupName = field 7
    ctx.body = message_body
    return ctx


# ---------------------------------------------------------------------------
# 元素解码
# ---------------------------------------------------------------------------


def decode_elements(body: bytes) -> list[dict[str, Any]]:
    """把 MessageBody 解码为内部元素列表（供 OneBot 段转换）。"""
    elements: list[dict[str, Any]] = []
    if not body:
        return elements
    rich_text = pb_bytes(body, 1)
    msg_content = pb_bytes(body, 2)
    if rich_text:
        for elem in pb_list(rich_text, 2):
            try:
                _decode_elem(elem, elements)
            except (ValueError, IndexError) as exc:
                log.debug('元素解码失败（已跳过）: %s', exc)
        _decode_ptt(rich_text, elements)
        _decode_not_online_file(rich_text, elements)
    if msg_content:
        _decode_msg_content(msg_content, elements)
    return elements


def _decode_elem(elem: bytes, out: list[dict[str, Any]]) -> None:
    text = pb_bytes(elem, 1)
    face = pb_bytes(elem, 2)
    not_online_image = pb_bytes(elem, 4)
    custom_face = pb_bytes(elem, 8)
    market_face = pb_bytes(elem, 6)
    rich_msg = pb_bytes(elem, 12)
    group_file = pb_bytes(elem, 13)
    light_app = pb_bytes(elem, 51)
    common_elem = pb_bytes(elem, 53)
    src_msg = pb_bytes(elem, 45)
    video_file = pb_bytes(elem, 19)

    if src_msg:
        seqs = pb_int_list(src_msg, 1)
        if seqs:
            out.append({'type': 'reply', 'seq': seqs[0], 'sender_uin': pb_int(src_msg, 2)})
    if text:
        content = pb_str(text, 1)
        attr6 = pb_bytes(text, 3)          # attr6Buf = field 3
        mention = _decode_mention(pb_bytes(text, 12))  # pbReserve = field 12
        is_at = (attr6 and len(attr6) > 11) or (mention and mention.get('type') in (1, 2))
        if is_at:
            target = 0
            if attr6 and len(attr6) > 11:
                target = int.from_bytes(attr6[7:11], 'big')
            if not target and mention:
                target = mention.get('uin', 0)
            out.append({'type': 'at', 'qq': target, 'text': content})
        elif content:
            out.append({'type': 'text', 'text': content})
    if face:
        index = pb_int(face, 1)
        if index >= 0:
            out.append({'type': 'face', 'id': index})
    if market_face and len(pb_bytes(market_face, 7)) == 16:
        out.append({
            'type': 'mface',
            'text': pb_str(market_face, 4),
            'emoji_id': pb_bytes(market_face, 7).hex(),
            'emoji_package_id': pb_int(market_face, 8),
            'emoji_key': pb_str(market_face, 10),
        })
    if not_online_image:
        md5 = pb_bytes(not_online_image, 7)
        if len(md5) == 16:
            md5_hex = md5.hex().upper()
            orig_url = pb_str(not_online_image, 15)
            out.append({
                'type': 'image',
                'url': _image_url(orig_url) or (f'http://gchat.qpic.cn/gchatpic_new/0/0-0-{md5_hex}/0'
                                                if md5_hex else ''),
                'file': pb_str(not_online_image, 1) or md5_hex,
                'file_size': pb_int(not_online_image, 2),
                'width': pb_int(not_online_image, 9),
                'height': pb_int(not_online_image, 8),
            })
    if custom_face:
        md5 = pb_bytes(custom_face, 13)
        if len(md5) == 16:
            md5_hex = md5.hex().upper()
            orig_url = pb_str(custom_face, 16)
            out.append({
                'type': 'image',
                'url': _image_url(orig_url) or (f'http://gchat.qpic.cn/gchatpic_new/0/0-0-{md5_hex}/0'
                                                if md5_hex else ''),
                'file': pb_str(custom_face, 2) or md5_hex,
                'file_size': pb_int(custom_face, 25),
                'width': pb_int(custom_face, 22),
                'height': pb_int(custom_face, 23),
            })
    if video_file:
        out.append({
            'type': 'video',
            'file': pb_str(video_file, 3),
            'file_id': pb_str(video_file, 1),
            'file_size': pb_int(video_file, 6),
            'duration': pb_int(video_file, 5),
            'width': pb_int(video_file, 7),
            'height': pb_int(video_file, 8),
        })
    if group_file:
        out.append({
            'type': 'file',
            'file_id': pb_str(group_file, 3),
            'name': pb_str(group_file, 1),
            'size': pb_int(group_file, 2),
        })
    if rich_msg:
        service_id = pb_int(rich_msg, 2)
        template = pb_bytes(rich_msg, 1)
        if template and template[0] in (0, 1):
            template = template[1:]
        out.append({'type': 'json' if service_id == 1 else 'xml',
                    'data': template.decode('utf-8', 'replace')})
    if light_app:
        payload = pb_bytes(light_app, 1)
        if payload and payload[0] in (0, 1):
            payload = payload[1:]
        out.append({'type': 'json', 'data': payload.decode('utf-8', 'replace')})
    if common_elem:
        service_type = pb_int(common_elem, 1)
        business_type = pb_int(common_elem, 3)
        pb_elem = pb_bytes(common_elem, 2)
        if service_type == 2:
            out.append({'type': 'poke', 'sub_type': business_type})
        elif service_type == 33 and pb_elem:
            face_id = pb_int(pb_elem, 1)  # QSmallFaceExtra.faceId = field 1
            if face_id >= 0:
                out.append({'type': 'face', 'id': face_id})


def _decode_mention(pb_reserve: bytes) -> dict[str, Any] | None:
    """MentionExtra: type=3 uin=4 field5=5 uid=9。"""
    if not pb_reserve:
        return None
    try:
        return {
            'type': pb_int(pb_reserve, 3),
            'uin': pb_int(pb_reserve, 4),
            'uid': pb_str(pb_reserve, 9),
        }
    except (ValueError, IndexError):
        return None


def _decode_ptt(rich_text: bytes, out: list[dict[str, Any]]) -> None:
    for ptt in pb_list(rich_text, 4):
        file_uuid = pb_bytes(ptt, 3)
        out.append({
            'type': 'record',
            'file': pb_str(ptt, 5) or file_uuid.decode('utf-8', 'replace'),
            'file_id': pb_str(ptt, 10) or pb_str(ptt, 14),
            'file_size': pb_int(ptt, 6),
            'duration': pb_int(ptt, 19),   # time = field 19
            'voice_format': pb_int(ptt, 29),
            'md5': pb_bytes(ptt, 4).hex(),
        })


def _decode_not_online_file(rich_text: bytes, out: list[dict[str, Any]]) -> None:
    for file_ in pb_list(rich_text, 3):
        out.append({
            'type': 'file',
            'file_id': pb_str(file_, 3),   # fileUuid = field 3
            'name': pb_str(file_, 5),      # fileName = field 5
            'size': pb_int(file_, 6),      # fileSize = field 6
            'md5': pb_bytes(file_, 4).hex(),
            'file_hash': pb_str(file_, 57),
        })


def _decode_msg_content(msg_content: bytes, out: list[dict[str, Any]]) -> None:
    """msgContent = FileExtra{ f1=file(NotOnlineFile) }。"""
    file_ = pb_bytes(msg_content, 1)
    if not file_:
        return
    file_uuid = pb_str(file_, 3)
    if not file_uuid:
        return
    out.append({
        'type': 'file',
        'file_id': file_uuid,
        'name': pb_str(file_, 5),
        'size': pb_int(file_, 6),
        'md5': pb_bytes(file_, 4).hex(),
        'file_hash': pb_str(file_, 57),
    })


def _image_url(orig_url: str) -> str:
    """与 SnowLuma makeImageUrl 对齐。"""
    if not orig_url:
        return ''
    if orig_url.startswith('http'):
        return orig_url
    if not orig_url.startswith('/'):
        return ''
    if 'rkey' in orig_url or 'fileid' in orig_url:
        return 'https://multimedia.nt.qq.com.cn' + orig_url
    return 'http://gchat.qpic.cn' + orig_url
