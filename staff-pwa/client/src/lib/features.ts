/** Candidate client contracts are implemented locally. These release gates stay
 * false until exact backend version, user-bound auth/RLS and hosted CORS pass.
 * No environment toggle or browser role can authorise enabling them.
 */
export const staffApiFeatures = {
  directMessages: {
    available: false,
    unavailableMessage: "院內直接訊息候選後端尚未完成實際環境驗證，因此暫不提供傳送或讀取對話。",
  },
  dutyRequestWindow: {
    available: false,
    unavailableMessage: "指定更期／休息日申請期候選後端尚未完成實際環境驗證，因此暫不提供此類提交。",
  },
} as const;

export type StaffApiFeature = keyof typeof staffApiFeatures;

export function featureAvailable(feature: StaffApiFeature) {
  return staffApiFeatures[feature].available;
}
