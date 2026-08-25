function numericId(value) {
  const text = String(value ?? "").trim();
  if (!text) return 0;
  const number = Number(text);
  return Number.isSafeInteger(number) ? number : text;
}

export function collectionValues(value) {
  if (value instanceof Map) return Array.from(value.values());
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") return Object.values(value);
  return [];
}

export function extractNativeGroupList(result) {
  const candidates = [
    result?.groupList, result?.groups,
    result?.data?.groupList, result?.data?.groups,
    result?.result?.groupList, result?.result?.groups,
    Array.isArray(result?.data) || result?.data instanceof Map ? result.data : undefined,
    Array.isArray(result?.result) || result?.result instanceof Map ? result.result : undefined,
  ];
  return candidates.find((value) => Array.isArray(value) || value instanceof Map);
}

export function extractNativeGroupDetail(result) {
  for (const value of [result?.data, result?.groupInfo, result?.detailInfo, result?.result, result]) {
    if (value && typeof value === "object" && !Array.isArray(value) &&
        (value.groupCode || value.groupId || value.group_id || value.groupName)) return value;
  }
  return undefined;
}

export function extractNativeMemberMap(result) {
  for (const value of [result?.result?.infos, result?.data?.infos, result?.infos, result?.members]) {
    if (value instanceof Map || Array.isArray(value) || (value && typeof value === "object")) return value;
  }
  return undefined;
}

/** 规范化 QQNT 的单对象与旧版多参数群成员列表回调。 */
export function normalizeNativeMemberListCallback(args, fallbackGroupId = "") {
  const values = Array.from(args || []);
  const first = values[0];
  const payload = first && typeof first === "object" && !Array.isArray(first) && !(first instanceof Map)
    ? first
    : null;
  const groupId = String(
    payload?.groupCode || payload?.groupId || payload?.sceneId ||
    (["string", "number", "bigint"].includes(typeof first) ? first : "") || fallbackGroupId || "",
  );
  const infos = extractNativeMemberMap(payload) ?? values[1] ??
    (first instanceof Map || Array.isArray(first) ? first : undefined);
  return { groupId, infos, payload };
}

/** 仅在两次完整快照中存在唯一新增成员时返回该成员。 */
export function findAddedGroupMember(previous, current) {
  const oldIds = new Set();
  for (const member of previous?.values?.() || []) {
    if (member?.uid) oldIds.add("uid:" + String(member.uid));
    if (member?.uin && String(member.uin) !== "0") oldIds.add("uin:" + String(member.uin));
  }
  const added = [];
  for (const member of current?.values?.() || []) {
    const known = (member?.uid && oldIds.has("uid:" + String(member.uid))) ||
      (member?.uin && String(member.uin) !== "0" && oldIds.has("uin:" + String(member.uin)));
    if (!known) added.push(member);
  }
  return added.length === 1 ? added[0] : null;
}

export function oneBotGroup(group, fallbackId = "") {
  const groupId = group?.groupCode ?? group?.group_id ?? group?.groupId ?? fallbackId;
  return {
    group_all_shut: Number(group?.groupShutupExpireTime ?? group?.shutUpAllTimestamp ?? group?.group_all_shut ?? 0) > 0 ? -1 : 0,
    group_remark: String(group?.remarkName ?? group?.group_remark ?? ""),
    group_id: numericId(groupId),
    group_name: String(group?.groupName ?? group?.group_name ?? ""),
    member_count: Number(group?.memberCount ?? group?.memberNum ?? group?.member_count ?? 0),
    max_member_count: Number(group?.maxMember ?? group?.maxMemberNum ?? group?.max_member_count ?? 0),
  };
}

function oneBotSex(value) {
  if (value === 1 || String(value).toLowerCase() === "male") return "male";
  if (value === 2 || String(value).toLowerCase() === "female") return "female";
  return "unknown";
}

function qqLevelValue(level) {
  if (typeof level === "number") return level;
  if (!level || typeof level !== "object") return 0;
  return Number(level.crownNum || 0) * 64 + Number(level.sunNum || 0) * 16 +
    Number(level.moonNum || 0) * 4 + Number(level.starNum || 0);
}

export function oneBotGroupMember(groupId, member) {
  return {
    group_id: numericId(groupId),
    user_id: numericId(member?.uin ?? member?.user_id),
    nickname: String(member?.nick ?? member?.nickname ?? ""),
    card: String(member?.cardName ?? member?.card ?? ""),
    sex: oneBotSex(member?.sex),
    age: Number(member?.age ?? 0),
    area: String(member?.area ?? ""),
    level: String(member?.memberRealLevel ?? member?.level ?? "0"),
    qq_level: qqLevelValue(member?.qqLevel),
    join_time: Number(member?.joinTime ?? member?.join_time ?? 0),
    last_sent_time: Number(member?.lastSpeakTime ?? member?.last_sent_time ?? 0),
    title_expire_time: Number(member?.titleExpireTime ?? member?.title_expire_time ?? 0),
    unfriendly: Boolean(member?.unfriendly ?? false),
    card_changeable: Boolean(member?.cardChangeable ?? member?.card_changeable ?? true),
    is_robot: Boolean(member?.isRobot ?? member?.is_robot ?? false),
    qage: Number(member?.qage ?? 0),
    shut_up_timestamp: Number(member?.shutUpTime ?? member?.shut_up_timestamp ?? 0),
    role: Number(member?.role) === 4 ? "owner" : Number(member?.role) === 3 ? "admin" : "member",
    title: String(member?.memberSpecialTitle ?? member?.title ?? ""),
  };
}

export function oneBotFriend(friend, fallbackUin = "") {
  const core = friend?.coreInfo || friend || {};
  const base = friend?.baseInfo || {};
  return {
    birthday_year: Number(base.birthday_year ?? 0),
    birthday_month: Number(base.birthday_month ?? 0),
    birthday_day: Number(base.birthday_day ?? 0),
    user_id: numericId(core.uin ?? friend?.uin ?? fallbackUin),
    age: Number(base.age ?? friend?.age ?? 0),
    phone_num: String(base.phoneNum ?? friend?.phone_num ?? ""),
    email: String(base.eMail ?? friend?.email ?? ""),
    category_id: Number(base.categoryId ?? friend?.category_id ?? 0),
    nickname: String(core.nick ?? friend?.nickname ?? ""),
    remark: String(core.remark ?? friend?.remark ?? core.nick ?? ""),
    sex: oneBotSex(base.sex ?? friend?.sex),
    level: qqLevelValue(friend?.qqLevel),
  };
}

export function groupAddOptionRequest(groupCode, addOption, question = "", answer = "") {
  const filter = Object.fromEntries([
    "noCodeFingerOpenFlag", "noFingerOpenFlag", "groupName", "classExt", "classText",
    "fingerMemo", "richFingerMemo", "tagRecord", "groupExtAdminNum", "flag", "groupMemo",
    "groupAioSkinUrl", "groupBoardSkinUrl", "groupCoverSkinUrl", "groupGrade",
    "activeMemberNum", "certificationType", "certificationText", "groupFace", "addOption",
    "shutUpTime", "groupTypeFlag", "appPrivilegeFlag", "appPrivilegeMask", "groupSecLevel",
    "groupSecLevelInfo", "subscriptionUin", "subscriptionUid", "allowMemberInvite",
    "groupQuestion", "groupAnswer", "groupFlagExt3", "groupFlagExt3Mask", "groupOpenAppid",
    "rootId", "msgLimitFrequency", "hlGuildAppid", "hlGuildSubType", "hlGuildOrgId",
    "groupFlagExt4", "groupFlagExt4Mask", "allianceId", "groupFlagPro1", "groupFlagPro1Mask",
  ].map((key) => [key, 0]));
  Object.assign(filter, {
    groupGeoInfo: { ownerUid: 0, setTime: 0, cityId: 0, longitude: 0, latitude: 0, geoContent: 0, poiId: 0 },
    groupNewGuideLines: { enabled: 0, content: 0 },
    groupExtOnly: { tribeId: 0, moneyForAddGroup: 0 },
    groupSchoolInfo: { location: 0, grade: 0, school: 0 },
    groupCardPrefix: { introduction: 0, rptPrefix: 0 },
  });
  filter.addOption = 1;
  if (addOption === 4 || addOption === 5) {
    filter.groupQuestion = 1;
    filter.groupAnswer = addOption === 4 ? 1 : 0;
  }

  const modifyInfo = {
    noCodeFingerOpenFlag: 0, noFingerOpenFlag: 0, groupName: "", classExt: 0,
    classText: "", fingerMemo: "", richFingerMemo: "", tagRecord: [],
    groupGeoInfo: { ownerUid: "", SetTime: 0, CityId: 0, Longitude: "", Latitude: "", GeoContent: "", poiId: "" },
    groupExtAdminNum: 0, flag: 0, groupMemo: "", groupAioSkinUrl: "", groupBoardSkinUrl: "",
    groupCoverSkinUrl: "", groupGrade: 0, activeMemberNum: 0, certificationType: 0,
    certificationText: "", groupNewGuideLines: { enabled: false, content: "" }, groupFace: 0,
    addOption, shutUpTime: 0, groupTypeFlag: 0, appPrivilegeFlag: 0, appPrivilegeMask: 0,
    groupExtOnly: { tribeId: 0, moneyForAddGroup: 0 }, groupSecLevel: 0, groupSecLevelInfo: 0,
    subscriptionUin: "", subscriptionUid: "", allowMemberInvite: 0,
    groupQuestion: addOption === 4 || addOption === 5 ? String(question || "") : "",
    groupAnswer: addOption === 4 ? String(answer || "") : "",
    groupFlagExt3: 0, groupFlagExt3Mask: 0, groupOpenAppid: 0, rootId: "",
    msgLimitFrequency: 0, hlGuildAppid: 0, hlGuildSubType: 0, hlGuildOrgId: 0,
    groupFlagExt4: 0, groupFlagExt4Mask: 0,
    groupSchoolInfo: { location: "", grade: 0, school: "" },
    groupCardPrefix: { introduction: "", rptPrefix: [] }, allianceId: "",
    groupFlagPro1: 0, groupFlagPro1Mask: 0,
  };
  return { groupCode: String(groupCode), filter, modifyInfo };
}

export function groupRobotOptionRequest(groupCode, memberSwitch, memberExamine) {
  const extInfo = {
    groupInfoExtSeq: 0, reserve: 0, luckyWordId: "", lightCharNum: 0, luckyWord: "",
    starId: 0, essentialMsgSwitch: 0, todoSeq: 0, blacklistExpireTime: 0,
    isLimitGroupRtc: 0, companyId: 0, hasGroupCustomPortrait: 0, bindGuildId: "",
    groupOwnerId: { memberUin: "", memberUid: "", memberQid: "" }, essentialMsgPrivilege: 0,
    msgEventSeq: "", inviteRobotSwitch: 0, gangUpId: "", qqMusicMedalSwitch: 0,
    showPlayTogetherSwitch: 0, groupFlagPro1: "", groupBindGuildIds: { guildIds: [] },
    viewedMsgDisappearTime: "", groupExtFlameData: { switchState: 0, state: 0, dayNums: [], version: 0, updateTime: "", isDisplayDayNum: false },
    groupBindGuildSwitch: 0, groupAioBindGuildId: "", groupExcludeGuildIds: { guildIds: [] },
    fullGroupExpansionSwitch: 0, fullGroupExpansionSeq: "", inviteRobotMemberSwitch: 0,
    inviteRobotMemberExamine: 0, groupSquareSwitch: 0,
  };
  const filter = Object.fromEntries(Object.keys(extInfo).map((key) => [key, 0]));
  if (memberSwitch !== undefined) {
    extInfo.inviteRobotMemberSwitch = Number(memberSwitch);
    filter.inviteRobotMemberSwitch = 1;
  }
  if (memberExamine !== undefined) {
    extInfo.inviteRobotMemberExamine = Number(memberExamine);
    filter.inviteRobotMemberExamine = 1;
  }
  return { info: { groupCode: String(groupCode), resultCode: 0, extInfo }, filter };
}

function baseGroupDetailRequest(groupCode) {
  const request = groupAddOptionRequest(groupCode, 0);
  request.filter.addOption = 0;
  return request;
}

function mergeMaskedFlag(currentFlag, requestedFlag, maskValue) {
  const mask = BigInt(maskValue);
  return Number((BigInt(currentFlag || 0) & ~mask) | (BigInt(requestedFlag || 0) & mask));
}

export function groupManagementRequests(groupCode, settings = {}, detail = {}) {
  const requests = [];
  let currentPrivilege = Number(detail.privilegeFlag || detail.appPrivilegeFlag || 0);
  let currentExt4 = Number(detail.groupFlagExt4 || 0);

  if (settings.memberInvite !== undefined) {
    const privilegeByPolicy = {
      disabled: 0x04000000,
      require_approval: 0,
      no_approval: 0x00100000,
      no_approval_under_100: 0x02000000,
    };
    if (!(settings.memberInvite in privilegeByPolicy)) {
      throw new TypeError("无效的群成员邀请策略");
    }
    const request = baseGroupDetailRequest(groupCode);
    request.filter.allowMemberInvite = 1;
    request.modifyInfo.allowMemberInvite = settings.memberInvite === "disabled" ? 0 : 1;
    request.filter.appPrivilegeFlag = 1;
    request.filter.appPrivilegeMask = 1;
    request.modifyInfo.appPrivilegeMask = 0x06100000;
    currentPrivilege = mergeMaskedFlag(
      currentPrivilege,
      privilegeByPolicy[settings.memberInvite],
      request.modifyInfo.appPrivilegeMask,
    );
    request.modifyInfo.appPrivilegeFlag = currentPrivilege;
    requests.push({ setting: "member_invite", param: request, operationType: 0 });
  }

  if (settings.newMembersSeeRecentHistory !== undefined) {
    const request = baseGroupDetailRequest(groupCode);
    request.filter.groupFlagExt4 = 1;
    request.filter.groupFlagExt4Mask = 1;
    request.modifyInfo.groupFlagExt4Mask = 0x4;
    const next = mergeMaskedFlag(
      currentExt4,
      settings.newMembersSeeRecentHistory ? 0x4 : 0,
      request.modifyInfo.groupFlagExt4Mask,
    );
    if (next !== currentExt4) {
      currentExt4 = next;
      request.modifyInfo.groupFlagExt4 = currentExt4;
      requests.push({ setting: "new_members_see_recent_history", param: request, operationType: 0 });
    }
  }

  const permissionSettings = [
    ["allow_member_upload_album", "allowMemberUploadAlbum", 0x1],
    ["allow_member_temporary_session", "allowMemberTemporarySession", 0x10000],
    ["allow_member_create_group", "allowMemberCreateGroup", 0x8000],
  ];
  for (const [setting, key, mask] of permissionSettings) {
    if (settings[key] === undefined) continue;
    const request = baseGroupDetailRequest(groupCode);
    request.filter.appPrivilegeFlag = 1;
    request.filter.appPrivilegeMask = 1;
    request.modifyInfo.appPrivilegeMask = mask;
    const next = mergeMaskedFlag(currentPrivilege, settings[key] ? 0 : mask, mask);
    if (next === currentPrivilege) continue;
    currentPrivilege = next;
    request.modifyInfo.appPrivilegeFlag = currentPrivilege;
    requests.push({ setting, param: request, operationType: 8 });
  }
  return requests;
}

export function groupSearchRequest(groupCode, noCodeFingerOpen, noFingerOpen) {
  const request = baseGroupDetailRequest(groupCode);
  if (noCodeFingerOpen !== undefined) {
    request.filter.noCodeFingerOpenFlag = 1;
    request.modifyInfo.noCodeFingerOpenFlag = Number(noCodeFingerOpen);
  }
  if (noFingerOpen !== undefined) {
    request.filter.noFingerOpenFlag = 1;
    request.modifyInfo.noFingerOpenFlag = Number(noFingerOpen);
  }
  return request;
}
