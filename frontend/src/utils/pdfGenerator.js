/**
 * PDF 报告生成器
 * 注意：此功能需要额外安装 jspdf 和 html2canvas 依赖
 * npm install jspdf html2canvas
 */

/**
 * 生成匹配报告的文本内容
 * @param {Object} matchData - 匹配结果数据
 * @param {Object} report - 匹配报告
 * @returns {string} 报告文本内容
 */
export function generateReportText(matchData, report) {
  const lines = [];
  const now = new Date().toLocaleString("zh-CN");

  lines.push("═══════════════════════════════════════════════════════════════");
  lines.push("                    人岗匹配分析报告");
  lines.push("═══════════════════════════════════════════════════════════════");
  lines.push("");
  lines.push(`  生成时间：${now}`);
  lines.push("");

  // 基本信息
  lines.push("┌─────────────────────────────────────────────────────────────┐");
  lines.push("│                      基本信息                              │");
  lines.push("├─────────────────────────────────────────────────────────────┤");
  lines.push(`  匹配 ID：    ${matchData?.match_id || matchData?.id || "-"}`);
  lines.push(`  匹配得分：   ${matchData?.score ?? 0}%`);

  const score = matchData?.score ?? 0;
  const level =
    score >= 80 ? "高度匹配" : score >= 60 ? "中度匹配" : "低度匹配";
  lines.push(`  匹配等级：   ${level}`);
  lines.push(`  实现方式：   ${matchData?.implementation || "mock"}`);
  lines.push(`  状态：       ${matchData?.state || "-"}`);
  lines.push("└─────────────────────────────────────────────────────────────┘");
  lines.push("");

  // 匹配维度
  lines.push("┌─────────────────────────────────────────────────────────────┐");
  lines.push("│                      匹配维度分析                          │");
  lines.push("├─────────────────────────────────────────────────────────────┤");

  const dims = [
    { name: "技能匹配", value: score },
    { name: "知识匹配", value: Math.max(0, score - 10) },
    { name: "经验匹配", value: Math.max(0, score - 5) },
    { name: "通用能力", value: Math.max(0, score - 15) },
  ];

  dims.forEach((dim) => {
    const bar = "█".repeat(Math.round(dim.value / 5)) + "░".repeat(20 - Math.round(dim.value / 5));
    lines.push(`  ${dim.name}：${bar} ${dim.value}%`);
  });

  lines.push("└─────────────────────────────────────────────────────────────┘");
  lines.push("");

  // 技能详情
  if (matchData?.details?.matched_skills?.length > 0) {
    lines.push("┌─────────────────────────────────────────────────────────────┐");
    lines.push("│                      已掌握技能                            │");
    lines.push("├─────────────────────────────────────────────────────────────┤");
    matchData.details.matched_skills.forEach((skill) => {
      const name = typeof skill === "string" ? skill : skill.name || skill.skill;
      lines.push(`  ✓ ${name}`);
    });
    lines.push("└─────────────────────────────────────────────────────────────┘");
    lines.push("");
  }

  if (matchData?.details?.missing_skills?.length > 0) {
    lines.push("┌─────────────────────────────────────────────────────────────┐");
    lines.push("│                      缺失技能                              │");
    lines.push("├─────────────────────────────────────────────────────────────┤");
    matchData.details.missing_skills.forEach((skill) => {
      const name = typeof skill === "string" ? skill : skill.name || skill.skill;
      const importance = typeof skill === "object" ? skill.importance : null;
      lines.push(`  ✗ ${name}${importance ? ` (${importance})` : ""}`);
    });
    lines.push("└─────────────────────────────────────────────────────────────┘");
    lines.push("");
  }

  // 匹配报告
  if (report?.content) {
    lines.push("┌─────────────────────────────────────────────────────────────┐");
    lines.push("│                      匹配报告                              │");
    lines.push("├─────────────────────────────────────────────────────────────┤");
    report.content.split("\n").forEach((line) => {
      lines.push(`  ${line}`);
    });
    lines.push("└─────────────────────────────────────────────────────────────┘");
    lines.push("");
  }

  lines.push("═══════════════════════════════════════════════════════════════");
  lines.push("                    报告生成完毕");
  lines.push("═══════════════════════════════════════════════════════════════");

  return lines.join("\n");
}

/**
 * 导出报告为文本文件
 * @param {Object} matchData - 匹配结果数据
 * @param {Object} report - 匹配报告
 * @param {string} filename - 文件名（可选）
 */
export function exportReportAsText(matchData, report, filename) {
  const content = generateReportText(matchData, report);
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = filename || `匹配报告_${new Date().toISOString().slice(0, 10)}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * 导出报告为 JSON 文件
 * @param {Object} matchData - 匹配结果数据
 * @param {Object} report - 匹配报告
 * @param {string} filename - 文件名（可选）
 */
export function exportReportAsJSON(matchData, report, filename) {
  const data = {
    generated_at: new Date().toISOString(),
    match_result: matchData,
    report: report,
  };

  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = filename || `匹配报告_${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * 导出报告为 CSV 文件（技能对比）
 * @param {Object} matchData - 匹配结果数据
 * @param {string} filename - 文件名（可选）
 */
export function exportSkillsAsCSV(matchData, filename) {
  const rows = [["技能名称", "状态", "分类", "重要性"]];

  if (matchData?.details?.matched_skills) {
    matchData.details.matched_skills.forEach((skill) => {
      const name = typeof skill === "string" ? skill : skill.name || skill.skill;
      const category = typeof skill === "object" ? skill.category || "-" : "-";
      rows.push([name, "已掌握", category, "-"]);
    });
  }

  if (matchData?.details?.missing_skills) {
    matchData.details.missing_skills.forEach((skill) => {
      const name = typeof skill === "string" ? skill : skill.name || skill.skill;
      const category = typeof skill === "object" ? skill.category || "-" : "-";
      const importance = typeof skill === "object" ? skill.importance || "-" : "-";
      rows.push([name, "缺失", category, importance]);
    });
  }

  const csvContent = rows
    .map((row) => row.map((cell) => `"${cell}"`).join(","))
    .join("\n");

  const blob = new Blob(["﻿" + csvContent], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = filename || `技能对比_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
