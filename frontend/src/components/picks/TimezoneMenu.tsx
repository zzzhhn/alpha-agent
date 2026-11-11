"use client";
import { TmSelectMenu } from "@/components/tm/TmSelectMenu";
import { useTimezonePreference } from "@/hooks/useTimezonePreference";

export default function TimezoneMenu({ zh }: { zh: boolean }) {
  const { preference, choose, localZone, ready } = useTimezonePreference();
  return <TmSelectMenu value={ready ? preference : "UTC"} onChange={choose}
    ariaLabel={zh ? "显示时区" : "Display timezone"} size="sm" menuMinWidth={280}
    options={[
      { value: "local", label: zh ? `本地（${localZone}）` : `Local (${localZone})` },
      { value: "Asia/Shanghai", label: zh ? "北京时间" : "Beijing time" },
      { value: "America/New_York", label: zh ? "纽约交易所时间" : "New York exchange time" },
      { value: "UTC", label: "UTC" },
    ]} />;
}
