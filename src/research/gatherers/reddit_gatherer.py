"""Reddit Gatherer Module

This module provides functionality to gather data from Reddit communities.
"""

import praw
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from .rate_limiter import RateLimiter
from .error_handler import ErrorHandler

logger = logging.getLogger(__name__)


class RedditGatherer:
    """Gathers data from Reddit communities with rate limiting and error handling."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        max_requests_per_hour: int = 600,
        max_retries: int = 3
    ):
        """Initialize Reddit gatherer.
        
        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            user_agent: User agent string for API requests
            max_requests_per_hour: Maximum API requests per hour
            max_retries: Maximum number of retry attempts for failed requests
        """
        self.rate_limiter = RateLimiter(max_requests_per_hour)
        self.error_handler = ErrorHandler(max_retries)
        
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        
        logger.info("RedditGatherer initialized")

    def _execute_with_rate_limit(self, func, *args, **kwargs):
        """Execute a function with rate limiting and error handling.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Result of function execution
        """
        self.rate_limiter.acquire()
        return self.error_handler.execute_with_retry(func, *args, **kwargs)

    def gather_subreddit_info(self, subreddit_name: str) -> Dict[str, Any]:
        """Gather information about a subreddit.
        
        Args:
            subreddit_name: Name of the subreddit
            
        Returns:
            Dictionary containing subreddit information with citation
        """
        logger.info(f"Gathering info for subreddit r/{subreddit_name}")
        
        try:
            def _get_subreddit():
                subreddit = self.reddit.subreddit(subreddit_name)
                # Access properties to trigger API call
                return {
                    "display_name": subreddit.display_name,
                    "title": subreddit.title,
                    "description": subreddit.public_description,
                    "subscribers": subreddit.subscribers,
                    "created_utc": subreddit.created_utc,
                    "url": f"https://reddit.com/r/{subreddit.display_name}"
                }
            
            data = self._execute_with_rate_limit(_get_subreddit)
            
            finding = {
                "type": "subreddit_info",
                "source": "reddit",
                "subreddit": subreddit_name,
                "url": data["url"],
                "gathered_at": datetime.utcnow().isoformat(),
                "data": {
                    "name": data["display_name"],
                    "title": data["title"],
                    "description": data["description"],
                    "subscribers": data["subscribers"],
                    "created_at": datetime.fromtimestamp(data["created_utc"]).isoformat()
                },
                "citation": {
                    "source_type": "reddit_subreddit",
                    "subreddit": subreddit_name,
                    "url": data["url"],
                    "accessed_at": datetime.utcnow().isoformat()
                }
            }
            
            logger.info(f"Successfully gathered info for r/{subreddit_name}")
            return finding
            
        except Exception as e:
            self.error_handler.handle_error(e, f"gathering subreddit info for r/{subreddit_name}")
            raise

    def gather_posts(
        self,
        subreddit_name: str,
        sort: str = "hot",
        time_filter: str = "all",
        max_posts: int = 100
    ) -> List[Dict[str, Any]]:
        """Gather posts from a subreddit.
        
        Args:
            subreddit_name: Name of the subreddit
            sort: Sort method (hot, new, top, rising, controversial)
            time_filter: Time filter for top/controversial (hour, day, week, month, year, all)
            max_posts: Maximum number of posts to gather
            
        Returns:
            List of dictionaries containing post information with citations
        """
        logger.info(f"Gathering posts from r/{subreddit_name} (sort={sort}, max={max_posts})")
        
        findings = []
        
        try:
            def _get_posts():
                subreddit = self.reddit.subreddit(subreddit_name)
                
                if sort == "hot":
                    return list(subreddit.hot(limit=max_posts))
                elif sort == "new":
                    return list(subreddit.new(limit=max_posts))
                elif sort == "top":
                    return list(subreddit.top(time_filter=time_filter, limit=max_posts))
                elif sort == "rising":
                    return list(subreddit.rising(limit=max_posts))
                elif sort == "controversial":
                    return list(subreddit.controversial(time_filter=time_filter, limit=max_posts))
                else:
                    raise ValueError(f"Invalid sort method: {sort}")
            
            posts = self._execute_with_rate_limit(_get_posts)
            
            for post in posts:
                finding = {
                    "type": "post",
                    "source": "reddit",
                    "subreddit": subreddit_name,
                    "url": f"https://reddit.com{post.permalink}",
                    "gathered_at": datetime.utcnow().isoformat(),
                    "data": {
                        "id": post.id,
                        "title": post.title,
                        "selftext": post.selftext,
                        "author": str(post.author) if post.author else "[deleted]",
                        "score": post.score,
                        "upvote_ratio": post.upvote_ratio,
                        "num_comments": post.num_comments,
                        "created_at": datetime.fromtimestamp(post.created_utc).isoformat(),
                        "is_self": post.is_self,
                        "url": post.url if not post.is_self else None,
                        "flair": post.link_flair_text
                    },
                    "citation": {
                        "source_type": "reddit_post",
                        "subreddit": subreddit_name,
                        "post_id": post.id,
                        "url": f"https://reddit.com{post.permalink}",
                        "accessed_at": datetime.utcnow().isoformat()
                    }
                }
                
                findings.append(finding)
            
            logger.info(f"Successfully gathered {len(findings)} posts from r/{subreddit_name}")
            return findings
            
        except Exception as e:
            self.error_handler.handle_error(e, f"gathering posts from r/{subreddit_name}")
            raise

    def gather_comments(
        self,
        subreddit_name: str,
        post_id: str,
        max_comments: int = 100
    ) -> List[Dict[str, Any]]:
        """Gather comments from a specific post.
        
        Args:
            subreddit_name: Name of the subreddit
            post_id: ID of the post
            max_comments: Maximum number of comments to gather
            
        Returns:
            List of dictionaries containing comment information with citations
        """
        logger.info(f"Gathering comments from post {post_id} in r/{subreddit_name}")
        
        findings = []
        
        try:
            def _get_comments():
                submission = self.reddit.submission(id=post_id)
                submission.comments.replace_more(limit=0)  # Don't fetch "more comments"
                return list(submission.comments.list())[:max_comments]
            
            comments = self._execute_with_rate_limit(_get_comments)
            
            for comment in comments:
                finding = {
                    "type": "comment",
                    "source": "reddit",
                    "subreddit": subreddit_name,
                    "post_id": post_id,
                    "url": f"https://reddit.com{comment.permalink}",
                    "gathered_at": datetime.utcnow().isoformat(),
                    "data": {
                        "id": comment.id,
                        "body": comment.body,
                        "author": str(comment.author) if comment.author else "[deleted]",
                        "score": comment.score,
                        "created_at": datetime.fromtimestamp(comment.created_utc).isoformat(),
                        "is_submitter": comment.is_submitter,
                        "parent_id": comment.parent_id
                    },
                    "citation": {
                        "source_type": "reddit_comment",
                        "subreddit": subreddit_name,
                        "post_id": post_id,
                        "comment_id": comment.id,
                        "url": f"https://reddit.com{comment.permalink}",
                        "accessed_at": datetime.utcnow().isoformat()
                    }
                }
                
                findings.append(finding)
            
            logger.info(f"Successfully gathered {len(findings)} comments from post {post_id}")
            return findings
            
        except Exception as e:
            self.error_handler.handle_error(e, f"gathering comments from post {post_id}")
            raise

    def search_subreddit(
        self,
        subreddit_name: str,
        query: str,
        sort: str = "relevance",
        time_filter: str = "all",
        max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """Search for posts in a subreddit.
        
        Args:
            subreddit_name: Name of the subreddit
            query: Search query
            sort: Sort method (relevance, hot, top, new, comments)
            time_filter: Time filter (hour, day, week, month, year, all)
            max_results: Maximum number of results to return
            
        Returns:
            List of dictionaries containing search results with citations
        """
        logger.info(f"Searching r/{subreddit_name} for '{query}' (sort={sort}, max={max_results})")
        
        findings = []
        
        try:
            def _search():
                subreddit = self.reddit.subreddit(subreddit_name)
                return list(subreddit.search(
                    query,
                    sort=sort,
                    time_filter=time_filter,
                    limit=max_results
                ))
            
            posts = self._execute_with_rate_limit(_search)
            
            for post in posts:
                finding = {
                    "type": "search_result",
                    "source": "reddit",
                    "subreddit": subreddit_name,
                    "query": query,
                    "url": f"https://reddit.com{post.permalink}",
                    "gathered_at": datetime.utcnow().isoformat(),
                    "data": {
                        "id": post.id,
                        "title": post.title,
                        "selftext": post.selftext,
                        "author": str(post.author) if post.author else "[deleted]",
                        "score": post.score,
                        "num_comments": post.num_comments,
                        "created_at": datetime.fromtimestamp(post.created_utc).isoformat()
                    },
                    "citation": {
                        "source_type": "reddit_search",
                        "subreddit": subreddit_name,
                        "query": query,
                        "post_id": post.id,
                        "url": f"https://reddit.com{post.permalink}",
                        "accessed_at": datetime.utcnow().isoformat()
                    }
                }
                
                findings.append(finding)
            
            logger.info(f"Successfully found {len(findings)} results for '{query}' in r/{subreddit_name}")
            return findings
            
        except Exception as e:
            self.error_handler.handle_error(e, f"searching r/{subreddit_name} for '{query}'")
            raise
