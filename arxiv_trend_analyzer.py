#!/usr/bin/env python3

import os
import json
import time
import logging
import threading
from typing import List, Dict, Any
import anthropic
import arxiv


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('arxiv_analyzer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def search_arxiv_papers(year: int, max_results: int = 200) -> List[Dict[str, Any]]:
    """Search arxiv papers by year and category using arxiv.query."""

    logger.info(f"Starting search for year {year} with max_results={max_results}")

    start_date = f"{year}0101"
    end_date = f"{year}1231"

    query = f'cat:cs.AI AND submittedDate:[{start_date} TO {end_date}]'
    logger.info(f"Arxiv query: {query}")

    try:
        logger.info(f"Executing arxiv.Client with max_results={max_results}...")
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate
        )

        results = list(client.results(search))[:max_results]
        logger.info(f"Found {len(results)} papers for year {year}")

        papers = []
        for i, result in enumerate(results):
            papers.append({
                "title": result.title,
                "abstract": result.summary,
                "published": result.published.strftime("%Y-%m-%d"),
                "categories": result.categories
            })

        logger.info(f"Successfully processed {len(papers)} papers")
        time.sleep(1)
        return papers

    except Exception as e:
        logger.error(f"Error searching arxiv for year {year}: {str(e)}", exc_info=True)
        return []

def filter_agent_papers(papers: List[Dict[str, Any]], year: int) -> Dict[str, int]:
    """Filter and count Agent-focused papers vs Other AI based on keywords."""

    agent_keywords = ["agent", "multi-agent", "agentic", "planning", "reasoning", "tool calling", "tool use"]

    agent_count = 0
    total_count = len(papers)

    for paper in papers:
        title = paper.get("title", "").lower()
        abstract = paper.get("abstract", "").lower()
        text = title + " " + abstract

        if any(keyword in text for keyword in agent_keywords):
            agent_count += 1

    return {
        "year": year,
        "total_papers": total_count,
        "agent_papers": agent_count
    }


def process_tool_call(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Process tool calls from Claude."""

    logger.info(f"Processing tool call: {tool_name} with input: {tool_input}")

    if tool_name == "search_and_filter_papers":
        year = tool_input.get("year")
        max_results = tool_input.get("max_results", 200)

        logger.info(f"Tool parameters: year={year}, max_results={max_results}")

        # Search papers
        papers = search_arxiv_papers(year, max_results)
        logger.info(f"Retrieved {len(papers)} papers for {year}")

        # Filter papers and return count summary
        filter_results = filter_agent_papers(papers, year)

        result = json.dumps(filter_results, ensure_ascii=False)
        other_count = filter_results['total_papers'] - filter_results['agent_papers']
        logger.info(f"Filter result: {filter_results['agent_papers']} Agent, {other_count} Other out of {filter_results['total_papers']} total")
        return result

    logger.warning(f"Unknown tool: {tool_name}")
    return f"Unknown tool: {tool_name}"

def run_analysis() -> str:
    """Main analysis function using advanced PTC with Claude. Returns markdown report."""

    logger.info("Starting arxiv trend analysis")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    logger.info("Using direct Anthropic API")
    client = anthropic.Anthropic(api_key=api_key)

    tools = [
        {
            "type": "code_execution_20250825",
            "name": "code_execution"
        },
        {
            "name": "search_and_filter_papers",
            "description": "Search arxiv papers and filter for Agent-related papers (returns only count summary)",
            "input_schema": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "Year to search (2020-2025)"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum papers to return",
                        "default": 200
                    }
                },
                "required": ["year"]
            }
        }
    ]

    initial_prompt = """タスク: cs.AI論文のAgent研究増加傾向分析（2020-2025）

目的: cs.AIカテゴリの論文(2020-2025年、各年200件)のタイトル・アブストラクトを分析し、Agent研究の増加傾向を示す

実行手順:
1. 2020年から2025年まで各年でsearch_and_filter_papersツールを呼び出し:
   - 各年のcs.AI論文を200件検索
   - Agent関連キーワードでフィルタリング実行
   - 集計結果を受け取り: {"year": 2020, "total_papers": 200, "agent_papers": 10}

2. code_executionで受け取った各年の結果からASCII棒グラフ生成:
   - numpy.histogramを使用してヒストグラムデータを作成
   - 年別Agent論文数と比率を計算
   - ASCII文字（█）を使って6年間の棒グラフを描画

最終出力形式（この形式のみ）:
```
2020年 : ███ 15論文 (7.50%)
2021年 : ████ 20論文 (10.00%)
2022年 : ██████ 30論文 (15.00%)
2023年 : ████████ 40論文 (20.00%)
2024年 : ██████████ 50論文 (25.00%)
2025年 : ████████████ 60論文 (30.00%)
```

重要:
- search_and_filter_papersツールを2020年から2025年で各1回ずつ（計6回）呼び出し
- code_executionでnumpyを活用:
  * import numpy as np
  * 各年のAgent論文数データを配列として作成
  * numpy.histogram()を使ってヒストグラムを計算
  * ヒストグラムの結果を基にASCII棒の長さを決定
- 受け取った結果でASCII棒グラフを作成
- 上記の形式のみを出力（他の説明や分析は不要）
- ASCII棒グラフは```コードブロックで囲む"""

    messages = [{"role": "user", "content": initial_prompt}]

    logger.info("Starting conversation with Claude")
    logger.info("=== INITIAL PROMPT ===")
    logger.info(initial_prompt)
    logger.info("========================")
    turn_count = 0
    markdown_result = ""

    while True:
        turn_count += 1
        logger.info(f"Turn {turn_count}: Sending request to Claude")

        # Log input message size and details
        total_chars = sum(len(str(msg)) for msg in messages)
        logger.info(f"=== INPUT SIZE (Turn {turn_count}) ===")
        logger.info(f"Messages count: {len(messages)}")
        logger.info(f"Total characters: {total_chars}")
        logger.info(f"Estimated input tokens: ~{total_chars // 4}")

        # Show recent message roles for debugging
        logger.info(f"Message roles: {[msg['role'] for msg in messages[-5:]]}")  # Last 5 messages
        logger.info(f"=====================================")

        try:
            # Use non-streaming for proper PTC behavior
            logger.info(f"Starting PTC request...")
            start_time = time.time()

            # Progress indicator for long requests
            def progress_indicator():
                dots = 0
                while not hasattr(progress_indicator, 'stop'):
                    elapsed = time.time() - start_time
                    print(f"\r[{elapsed:.1f}s] Processing PTC{'.' * (dots % 4)}", end='', flush=True)
                    dots += 1
                    time.sleep(1)

            progress_thread = threading.Thread(target=progress_indicator)
            progress_thread.daemon = True
            progress_thread.start()

            # Use non-streaming API with extended timeout for PTC
            response = client.beta.messages.create(
                betas=["advanced-tool-use-2025-11-20"],
                model="claude-sonnet-4-5-20250929",
                max_tokens=10000,
                tools=tools,
                messages=messages,
                timeout=300  # 5 minutes timeout
            )

            # Stop progress indicator
            progress_indicator.stop = True
            elapsed_total = time.time() - start_time
            logger.info(f"PTC request completed in {elapsed_total:.2f} seconds")

            if not response:
                logger.error("No response received")
                break

            # Check if response has expected attributes
            if not hasattr(response, 'stop_reason'):
                logger.error(f"Response object type: {type(response)}")
                logger.error(f"Response attributes: {dir(response)}")
                break

            logger.info(f"Received response with stop_reason: {response.stop_reason}")

            # Print token usage
            if hasattr(response, 'usage'):
                logger.info(f"=== TOKEN USAGE (Turn {turn_count}) ===")
                logger.info(f"Input tokens: {response.usage.input_tokens}")
                logger.info(f"Output tokens: {response.usage.output_tokens}")
                logger.info(f"Total tokens: {response.usage.input_tokens + response.usage.output_tokens}")
                logger.info(f"=====================================")

            # Log response metadata
            logger.info(f"=== RESPONSE METADATA ===")
            logger.info(f"Model: {response.model}")
            logger.info(f"Stop reason: {response.stop_reason}")
            if hasattr(response, 'id'):
                logger.info(f"Response ID: {response.id}")
            logger.info(f"Content blocks: {len(response.content)}")
            logger.info(f"========================")

            logger.info(f"=== CLAUDE RESPONSE (Turn {turn_count}) ===")
            for i, block in enumerate(response.content):
                logger.info(f"Block {i} ({block.type}):")
                if block.type == "text":
                    logger.info(f"Text: {block.text[:200]}{'...' if len(block.text) > 200 else ''}")
                    # Collect only the final markdown result with ASCII bar chart
                    if "```" in block.text and ("年" in block.text and "論文" in block.text):
                        markdown_result = block.text  # Only keep the final result
                elif block.type == "tool_use":
                    logger.info(f"Tool: {block.name}")
                    logger.info(f"Input: {block.input}")
                    logger.info(f"ID: {block.id}")
                elif block.type == "server_tool_use":
                    logger.info(f"Server Tool: {block.name}")
                    logger.info(f"ID: {block.id}")
                    if hasattr(block, 'input'):
                        logger.info(f"Input: {block.input}")
                        # Log Python code if it's code execution
                        if block.name in ['text_editor_code_execution', 'bash_code_execution']:
                            if 'file_text' in block.input:
                                logger.info(f"Generated Python Code:")
                                logger.info(block.input['file_text'])
                            elif 'command' in block.input:
                                logger.info(f"Bash Command: {block.input['command']}")
                    # Log full content for code generation verification
                    logger.info("Full server tool content:")
                    for attr in ['input', 'name', 'id', 'type']:
                        if hasattr(block, attr):
                            value = getattr(block, attr)
                            logger.info(f"  {attr}: {value}")
                elif hasattr(block, 'type') and 'tool_result' in block.type:
                    logger.info(f"Tool Result Type: {block.type}")
                    if hasattr(block, 'tool_use_id'):
                        logger.info(f"Tool Use ID: {block.tool_use_id}")
                    if hasattr(block, 'content'):
                        content = str(block.content)[:500]  # 増やして詳細表示
                        logger.info(f"Content: {content}{'...' if len(str(block.content)) > 500 else ''}")
                        # Log stdout if available (for bash execution results)
                        if hasattr(block, 'content') and hasattr(block.content, 'stdout'):
                            logger.info(f"Stdout: {block.content.stdout}")
                else:
                    logger.info(f"Unknown block type: {block.type}")
                    # Log all available attributes for unknown types
                    logger.info("All attributes:")
                    for attr in dir(block):
                        if not attr.startswith('_'):
                            try:
                                value = getattr(block, attr)
                                if not callable(value):
                                    logger.info(f"  {attr}: {value}")
                            except:
                                pass
                logger.info("---")
            logger.info(f"==========================================")

            if response.stop_reason == "end_turn":
                logger.info("Conversation completed")
                break

            if response.stop_reason == "tool_use":
                logger.info("Processing tool uses")
                tool_results = []

                for i, block in enumerate(response.content):
                    logger.debug(f"Processing content block {i}: type={block.type}")

                    if block.type == "tool_use":
                        logger.info(f"Executing tool: {block.name}")
                        result = process_tool_call(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })
                        logger.info(f"Tool {block.name} execution completed")

                    elif block.type == "server_tool_use":
                        logger.info(f"Server tool executed: {block.name}")
                        # Server tool results are handled automatically, don't add to tool_results

                messages.append({"role": "assistant", "content": response.content})
                if tool_results:  # Only add if there are actual tool results
                    messages.append({"role": "user", "content": tool_results})

                logger.info(f"Added {len(tool_results)} tool results to conversation")
                logger.info(f"Total conversation length: {len(messages)} messages")


        except Exception as e:
            logger.error(f"Error during API call on turn {turn_count}: {str(e)}", exc_info=True)
            logger.error("Stopping due to repeated API errors")
            break

    # Analysis completed - return markdown result
    logger.info("Analysis completed successfully")
    return markdown_result.strip() if markdown_result else "# Analysis completed but no markdown result found"


def main():
    """Entry point for the application."""
    logger.info("Application started")

    try:
        markdown_result = run_analysis()

        # Save markdown result to output.md
        output_path = "output.md"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_result)

        logger.info(f"Analysis completed and saved to {output_path}")
        logger.info(f"Saved {len(markdown_result)} characters")

    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application failed: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    main()