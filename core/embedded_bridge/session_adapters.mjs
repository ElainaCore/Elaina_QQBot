// QQ 会在整个会话生命周期内保留这些对象的原生引用。
export class GlobalAdapter {
  onLog() {}
  onGetSrvCalTime() {}
  onShowErrUITips() {}
  fixPicImgType() {}
  getAppSetting() {}
  onInstallFinished() {}
  onUpdateGeneralFlag() {}
  onGetOfflineMsg() {}
}

export class O3MiscListener {
  getOnAmgomDataPiece() {}
}

export class NodeIKernelLoginListener {
  onLoginConnected() {}
  onLoginDisConnected() {}
  onLoginConnecting() {}
  onQRCodeGetPicture() {}
  onQRCodeLoginPollingStarted() {}
  onQRCodeSessionUserScaned() {}
  onQRCodeLoginSucceed() {}
  onQRCodeSessionFailed() {}
  onLoginFailed() {}
  onLogoutSucceed() {}
  onLogoutFailed() {}
  onUserLoggedIn() {}
  onQRCodeSessionQuickLoginFailed() {}
  onPasswordLoginFailed() {}
  OnConfirmUnusualDeviceFailed() {}
  onQQLoginNumLimited() {}
  onLoginState() {}
  onLoginRecordUpdate() {}
}

export const LoginListener = NodeIKernelLoginListener;

export class SessionDependsAdapter {
  onMSFStatusChange() {}
  onMSFSsoError() {}
  getGroupCode() {}
}

export class SessionDispatcherAdapter {
  dispatchRequest() {}
  dispatchCall() {}
  dispatchCallWithJson() {}
}

export class SessionListener {
  onNTSessionCreate() {}
  onGProSessionCreate() {}
  onSessionInitComplete() {}
  onOpentelemetryInit() {}
  onUserOnlineResult() {}
  onGetSelfTinyId() {}
}

export class MessageListener {
  onAddSendMsg() {}
  onBroadcastHelperDownloadComplete() {}
  onBroadcastHelperProgressUpdate() {}
  onChannelFreqLimitInfoUpdate() {}
  onContactUnreadCntUpdate() {}
  onCustomWithdrawConfigUpdate() {}
  onDraftUpdate() {}
  onEmojiDownloadComplete() {}
  onEmojiResourceUpdate() {}
  onFeedEventUpdate() {}
  onFileMsgCome() {}
  onFirstViewDirectMsgUpdate() {}
  onFirstViewGroupGuildMapping() {}
  onGrabPasswordRedBag() {}
  onGroupFileInfoAdd() {}
  onGroupFileInfoUpdate() {}
  onGroupGuildUpdate() {}
  onGroupTransferInfoAdd() {}
  onGroupTransferInfoUpdate() {}
  onGuildInteractiveUpdate() {}
  onGuildMsgAbFlagChanged() {}
  onGuildNotificationAbstractUpdate() {}
  onHitCsRelatedEmojiResult() {}
  onHitEmojiKeywordResult() {}
  onHitRelatedEmojiResult() {}
  onImportOldDbProgressUpdate() {}
  onInputStatusPush() {}
  onKickedOffLine() {}
  onLineDev() {}
  onLogLevelChanged() {}
  onMsgAbstractUpdate() {}
  onMsgBoxChanged() {}
  onMsgDelete() {}
  onMsgEventListUpdate() {}
  onMsgInfoListAdd() {}
  onMsgInfoListUpdate() {}
  onMsgQRCodeStatusChanged() {}
  onMsgRecall() {}
  onMsgSecurityNotify() {}
  onMsgSettingUpdate() {}
  onNtFirstViewMsgSyncEnd() {}
  onNtMsgSyncEnd() {}
  onNtMsgSyncStart() {}
  onReadFeedEventUpdate() {}
  onRecvGroupGuildFlag() {}
  onRecvMsg() {}
  onRecvMsgSvrRspTransInfo() {}
  onRecvOnlineFileMsg() {}
  onRecvS2CMsg() {}
  onRecvSysMsg() {}
  onRecvUDCFlag() {}
  onRichMediaDownloadComplete() {}
  onRichMediaProgerssUpdate() {}
  onRichMediaUploadComplete() {}
  onSearchGroupFileInfoUpdate() {}
  onSendMsgError() {}
  onSysMsgNotification() {}
  onTempChatInfoUpdate() {}
  onUnreadCntAfterFirstView() {}
  onUnreadCntUpdate() {}
  onUserChannelTabStatusChanged() {}
  onUserOnlineStatusChanged() {}
  onUserTabStatusChanged() {}
  onlineStatusBigIconDownloadPush() {}
  onlineStatusSmallIconDownloadPush() {}
  onUserSecQualityChanged() {}
  onMsgWithRichLinkInfoUpdate() {}
  onRedTouchChanged() {}
  onBroadcastHelperProgerssUpdate() {}
}
