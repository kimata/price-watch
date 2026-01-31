#!/usr/bin/env python3
"""Git リポジトリへのファイル同期機能.

GitLab/GitHub REST API を使用してファイルをリモートリポジトリに同期します。
"""

from __future__ import annotations

import base64
import logging
import re
import urllib.parse
from dataclasses import dataclass

import requests
import urllib3

import price_watch.config

# 自己署名証明書使用時の警告を抑制
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass(frozen=True)
class GitSyncResult:
    """Git 同期結果"""

    success: bool
    commit_url: str | None = None
    error: str | None = None


def _is_github_url(remote_url: str) -> bool:
    """URL が GitHub かどうかを判定."""
    return "github.com" in remote_url


def _parse_gitlab_project_path(remote_url: str) -> tuple[str, str]:
    """GitLab URL からベース URL とプロジェクトパスを取得.

    Args:
        remote_url: リポジトリ URL (例: https://gitlab.example.com/user/repo.git)

    Returns:
        (base_url, project_path) のタプル
    """
    # .git サフィックスを除去
    url = remote_url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]

    # URL をパース
    parsed = urllib.parse.urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    project_path = parsed.path.lstrip("/")

    return base_url, project_path


def _parse_github_repo(remote_url: str) -> tuple[str, str]:
    """GitHub URL から owner と repo を取得.

    Args:
        remote_url: リポジトリ URL (例: https://github.com/owner/repo.git)

    Returns:
        (owner, repo) のタプル
    """
    # .git サフィックスを除去
    url = remote_url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]

    # パスから owner/repo を抽出
    match = re.search(r"github\.com[/:]([^/]+)/([^/]+)", url)
    if not match:
        msg = f"Invalid GitHub URL: {remote_url}"
        raise ValueError(msg)

    return match.group(1), match.group(2)


def _sync_to_gitlab(
    config: price_watch.config.GitSyncConfig,
    content: str,
    commit_message: str,
) -> GitSyncResult:
    """GitLab にファイルを同期.

    Args:
        config: Git 同期設定
        content: ファイル内容
        commit_message: コミットメッセージ

    Returns:
        同期結果
    """
    base_url, project_path = _parse_gitlab_project_path(config.remote_url)
    encoded_path = urllib.parse.quote(project_path, safe="")

    # まず既存ファイルの情報を取得（存在確認）
    file_path_encoded = urllib.parse.quote(config.file_path, safe="")
    get_url = f"{base_url}/api/v4/projects/{encoded_path}/repository/files/{file_path_encoded}"
    headers = {"PRIVATE-TOKEN": config.access_token}

    try:
        # ファイルが存在するか確認
        # NOTE: 自己署名証明書対応のため verify=False を設定
        response = requests.get(
            get_url,
            headers=headers,
            params={"ref": config.branch},
            timeout=30,
            verify=False,  # noqa: S501
        )
        file_exists = response.status_code == 200

        # ファイルを作成または更新
        api_url = f"{base_url}/api/v4/projects/{encoded_path}/repository/files/{file_path_encoded}"
        payload = {
            "branch": config.branch,
            "content": content,
            "commit_message": commit_message,
        }

        if file_exists:
            # 更新
            response = requests.put(api_url, headers=headers, json=payload, timeout=30, verify=False)  # noqa: S501
        else:
            # 新規作成
            response = requests.post(api_url, headers=headers, json=payload, timeout=30, verify=False)  # noqa: S501

        if response.status_code in (200, 201):
            # コミット URL を構築
            # GitLab API は file_path を返すが、commit_id は返さないことがある
            # コミット URL は commits エンドポイントから取得する必要があるが、
            # 簡略化のため、branch のコミット一覧 URL を返す
            commit_url = f"{base_url}/{project_path}/-/commits/{config.branch}"
            logging.info("Successfully pushed to GitLab: %s", commit_url)
            return GitSyncResult(success=True, commit_url=commit_url)

        error_msg = f"GitLab API error: {response.status_code} - {response.text}"
        logging.error(error_msg)
        return GitSyncResult(success=False, error=error_msg)

    except requests.RequestException as e:
        error_msg = f"GitLab request failed: {e}"
        logging.exception(error_msg)
        return GitSyncResult(success=False, error=error_msg)


def _sync_to_github(
    config: price_watch.config.GitSyncConfig,
    content: str,
    commit_message: str,
) -> GitSyncResult:
    """GitHub にファイルを同期.

    Args:
        config: Git 同期設定
        content: ファイル内容
        commit_message: コミットメッセージ

    Returns:
        同期結果
    """
    owner, repo = _parse_github_repo(config.remote_url)

    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{config.file_path}"
    headers = {
        "Authorization": f"Bearer {config.access_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        # まず既存ファイルの SHA を取得（更新に必要）
        response = requests.get(
            api_url,
            headers=headers,
            params={"ref": config.branch},
            timeout=30,
        )
        sha = None
        if response.status_code == 200:
            sha = response.json().get("sha")

        # ファイルを作成または更新
        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": config.branch,
        }
        if sha:
            payload["sha"] = sha

        response = requests.put(api_url, headers=headers, json=payload, timeout=30)

        if response.status_code in (200, 201):
            result_data = response.json()
            commit_url = result_data.get("commit", {}).get("html_url")
            logging.info("Successfully pushed to GitHub: %s", commit_url)
            return GitSyncResult(success=True, commit_url=commit_url)

        error_msg = f"GitHub API error: {response.status_code} - {response.text}"
        logging.error(error_msg)
        return GitSyncResult(success=False, error=error_msg)

    except requests.RequestException as e:
        error_msg = f"GitHub request failed: {e}"
        logging.exception(error_msg)
        return GitSyncResult(success=False, error=error_msg)


def sync_to_remote(
    config: price_watch.config.GitSyncConfig,
    content: str,
    commit_message: str = "Update target.yaml via Web UI",
) -> GitSyncResult:
    """ファイルをリモートリポジトリに同期.

    Args:
        config: Git 同期設定
        content: ファイル内容
        commit_message: コミットメッセージ

    Returns:
        同期結果
    """
    if _is_github_url(config.remote_url):
        return _sync_to_github(config, content, commit_message)
    return _sync_to_gitlab(config, content, commit_message)
