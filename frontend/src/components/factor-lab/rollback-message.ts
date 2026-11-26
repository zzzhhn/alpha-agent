import { ApiException } from "@/lib/api/client";

export function rollbackMessage(error: unknown, zh: boolean, fallback: string): string {
  if (error instanceof ApiException && error.status === 409) {
    switch (error.body.detail) {
      case "proposal already rolled back":
        return zh ? "这条提案已经回滚。" : "This proposal has already been rolled back.";
      case "approved version is no longer current":
        return zh ? "当前配置已有后续变更，请核对最新版本。" : "A newer configuration is active. Check its history.";
      case "current config lineage requires review":
      case "approval lineage requires review":
        return zh ? "缺少可核验的版本记录，请先核对变更历史。" : "The version record is incomplete. Review the change history.";
    }
  }
  return error instanceof Error ? error.message : fallback;
}
