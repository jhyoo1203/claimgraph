import { readFileSync } from "node:fs";

const notionApiBase = process.env.NOTION_API_BASE ?? "https://api.notion.com/v1";
const notionVersion = process.env.NOTION_VERSION ?? "2026-03-11";
const branchPattern = /^feature\/CG-(\d+)$/;

function readEvent() {
  if (process.env.EVENT_JSON) {
    return JSON.parse(process.env.EVENT_JSON);
  }

  const eventPath = process.env.GITHUB_EVENT_PATH;
  if (!eventPath) {
    return {};
  }

  return JSON.parse(readFileSync(eventPath, "utf8"));
}

function branchFromEvent(eventName, event) {
  if (eventName === "push") {
    return (process.env.GITHUB_REF ?? "").replace(/^refs\/heads\//, "");
  }

  if (eventName === "pull_request") {
    return event.pull_request?.head?.ref ?? "";
  }

  return "";
}

function transitionFromEvent(eventName, event, branch) {
  const match = branch.match(branchPattern);
  if (!match) {
    return { status: null, issueNumber: null, reason: `ignored branch: ${branch || "<empty>"}` };
  }

  const issueNumber = Number(match[1]);

  if (eventName === "push") {
    return { status: "In Progress", issueNumber };
  }

  if (eventName !== "pull_request") {
    return { status: null, issueNumber: null, reason: `ignored event: ${eventName || "<empty>"}` };
  }

  if (event.pull_request?.base?.ref !== "develop") {
    return { status: null, issueNumber: null, reason: "ignored pull request outside develop" };
  }

  if (["opened", "reopened", "ready_for_review"].includes(event.action)) {
    return { status: "Review", issueNumber };
  }

  if (event.action === "closed" && event.pull_request?.merged === true) {
    return { status: "Done", issueNumber };
  }

  return { status: null, issueNumber: null, reason: `ignored pull request action: ${event.action || "<empty>"}` };
}

async function notionRequest(path, options = {}) {
  const response = await fetch(`${notionApiBase}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${process.env.NOTION_TOKEN}`,
      "Content-Type": "application/json",
      "Notion-Version": notionVersion,
      ...(options.headers ?? {})
    }
  });

  if (!response.ok) {
    throw new Error(`Notion API request failed with HTTP ${response.status}`);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

async function findWorkItem(issueNumber) {
  const dataSourceId = process.env.NOTION_DATA_SOURCE_ID;
  const response = await notionRequest(`/data_sources/${dataSourceId}/query`, {
    method: "POST",
    body: JSON.stringify({
      result_type: "page",
      page_size: 10,
      filter: {
        property: "ID",
        unique_id: { equals: issueNumber }
      }
    })
  });

  const pages = response.results ?? [];
  if (pages.length === 0) {
    return null;
  }

  if (pages.length > 1) {
    throw new Error(`Multiple Notion work items found for CG-${issueNumber}`);
  }

  return pages[0];
}

async function updateWorkItem(pageId, branch, status, pullRequestUrl) {
  const properties = {
    Status: { select: { name: status } },
    Branch: {
      rich_text: [
        {
          type: "text",
          text: { content: branch }
        }
      ]
    }
  };

  if (pullRequestUrl) {
    properties.PR = { url: pullRequestUrl };
  }

  await notionRequest(`/pages/${pageId}`, {
    method: "PATCH",
    body: JSON.stringify({ properties })
  });
}

async function main() {
  const eventName = process.env.GITHUB_EVENT_NAME ?? "";
  const event = readEvent();
  const branch = branchFromEvent(eventName, event);
  const transition = transitionFromEvent(eventName, event, branch);

  if (!transition.status) {
    console.log(`Notion sync skipped: ${transition.reason}`);
    return;
  }

  if (!process.env.NOTION_TOKEN || !process.env.NOTION_DATA_SOURCE_ID) {
    throw new Error("NOTION_TOKEN and NOTION_DATA_SOURCE_ID are required for Notion sync");
  }

  const issueKey = `CG-${transition.issueNumber}`;
  const pullRequestUrl = event.pull_request?.html_url ?? "";

  if (process.env.DRY_RUN === "true") {
    console.log(`DRY_RUN: ${issueKey} ${branch} -> ${transition.status}${pullRequestUrl ? ` (${pullRequestUrl})` : ""}`);
    return;
  }

  const workItem = await findWorkItem(transition.issueNumber);
  if (!workItem) {
    console.warn(`::warning::No Notion work item found for ${issueKey}; nothing was updated`);
    return;
  }

  await updateWorkItem(workItem.id, branch, transition.status, pullRequestUrl);
  console.log(`Notion work item ${issueKey} updated to ${transition.status}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
