"""Reddit Discovery Module.

This module provides the RedditDiscovery class for discovering relevant
posts and discussions on Reddit.
"""

import requests
from typing import Dict, List, Optional
from dataclasses import dataclass
import time


@dataclass
class RedditPost:
    """Represents a Reddit post."""
    
    title: str
    subreddit: str
    author: str
    url: str
    score: int
    num_comments: int
    created_utc: float
    selftext: Optional[str]
    permalink: str
    
    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            "title": self.title,
            "subreddit": self.subreddit,
            "author": self.author,
            "url": self.url,
            "score": self.score,
            "num_comments": self.num_comments,
            "created_utc": self.created_utc,
            "selftext": self.selftext,
            "permalink": self.permalink
        }


@dataclass
class RedditComment:
    """Represents a Reddit comment."""
    
    author: str
    body: str
    score: int
    created_utc: float
    permalink: str
    
    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            "author": self.author,
            "body": self.body,
            "score": self.score,
            "created_utc": self.created_utc,
            "permalink": self.permalink
        }


class RedditDiscovery:
    """Discovers relevant posts and discussions on Reddit."""
    
    def __init__(self, user_agent: str = "ResearchBot/1.0"):
        """Initialize Reddit discovery.
        
        Args:
            user_agent: User agent string for Reddit API requests
        """
        self.user_agent = user_agent
        self.base_url = "https://www.reddit.com"
        self.headers = {
            "User-Agent": user_agent
        }
        self.last_request_time = 0
        self.min_request_interval = 2  # Seconds between requests
    
    def search_posts(self, query: str, subreddit: Optional[str] = None,
                    sort: str = "relevance", time_filter: str = "all",
                    max_results: int = 25) -> List[RedditPost]:
        """Search for posts matching the query.
        
        Args:
            query: Search query
            subreddit: Limit search to specific subreddit
            sort: Sort method (relevance, hot, top, new, comments)
            time_filter: Time filter (hour, day, week, month, year, all)
            max_results: Maximum number of results to return
            
        Returns:
            List of matching posts
        """
        self._rate_limit()
        
        if subreddit:
            url = f"{self.base_url}/r/{subreddit}/search.json"
        else:
            url = f"{self.base_url}/search.json"
        
        params = {
            "q": query,
            "sort": sort,
            "t": time_filter,
            "limit": min(max_results, 100),
            "raw_json": 1
        }
        
        if subreddit:
            params["restrict_sr"] = "on"
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                posts = []
                
                for child in data.get("data", {}).get("children", []):
                    post_data = child.get("data", {})
                    
                    post = RedditPost(
                        title=post_data.get("title", ""),
                        subreddit=post_data.get("subreddit", ""),
                        author=post_data.get("author", ""),
                        url=post_data.get("url", ""),
                        score=post_data.get("score", 0),
                        num_comments=post_data.get("num_comments", 0),
                        created_utc=post_data.get("created_utc", 0),
                        selftext=post_data.get("selftext"),
                        permalink=f"{self.base_url}{post_data.get('permalink', '')}"
                    )
                    posts.append(post)
                
                return posts[:max_results]
            else:
                return []
        
        except requests.RequestException:
            return []
    
    def get_subreddit_posts(self, subreddit: str, sort: str = "hot",
                           time_filter: str = "day", max_results: int = 25) -> List[RedditPost]:
        """Get posts from a specific subreddit.
        
        Args:
            subreddit: Subreddit name
            sort: Sort method (hot, new, top, rising)
            time_filter: Time filter for 'top' sort (hour, day, week, month, year, all)
            max_results: Maximum number of results to return
            
        Returns:
            List of posts from the subreddit
        """
        self._rate_limit()
        
        url = f"{self.base_url}/r/{subreddit}/{sort}.json"
        
        params = {
            "limit": min(max_results, 100),
            "raw_json": 1
        }
        
        if sort == "top":
            params["t"] = time_filter
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                posts = []
                
                for child in data.get("data", {}).get("children", []):
                    post_data = child.get("data", {})
                    
                    post = RedditPost(
                        title=post_data.get("title", ""),
                        subreddit=post_data.get("subreddit", ""),
                        author=post_data.get("author", ""),
                        url=post_data.get("url", ""),
                        score=post_data.get("score", 0),
                        num_comments=post_data.get("num_comments", 0),
                        created_utc=post_data.get("created_utc", 0),
                        selftext=post_data.get("selftext"),
                        permalink=f"{self.base_url}{post_data.get('permalink', '')}"
                    )
                    posts.append(post)
                
                return posts[:max_results]
            else:
                return []
        
        except requests.RequestException:
            return []
    
    def get_post_comments(self, subreddit: str, post_id: str,
                         sort: str = "best", max_results: int = 50) -> List[RedditComment]:
        """Get comments from a specific post.
        
        Args:
            subreddit: Subreddit name
            post_id: Post ID
            sort: Sort method (best, top, new, controversial, old, qa)
            max_results: Maximum number of comments to return
            
        Returns:
            List of comments from the post
        """
        self._rate_limit()
        
        url = f"{self.base_url}/r/{subreddit}/comments/{post_id}.json"
        
        params = {
            "sort": sort,
            "limit": min(max_results, 100),
            "raw_json": 1
        }
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                comments = []
                
                # Reddit returns [post_data, comments_data]
                if len(data) > 1:
                    comments_data = data[1]
                    self._extract_comments(comments_data, comments, max_results)
                
                return comments[:max_results]
            else:
                return []
        
        except requests.RequestException:
            return []
    
    def _extract_comments(self, data: Dict, comments: List[RedditComment],
                         max_results: int, depth: int = 0):
        """Recursively extract comments from nested structure.
        
        Args:
            data: Comment data structure
            comments: List to append comments to
            max_results: Maximum number of comments to extract
            depth: Current recursion depth
        """
        if len(comments) >= max_results or depth > 10:
            return
        
        for child in data.get("data", {}).get("children", []):
            if len(comments) >= max_results:
                break
            
            comment_data = child.get("data", {})
            
            # Skip "more comments" entries
            if child.get("kind") != "t1":
                continue
            
            comment = RedditComment(
                author=comment_data.get("author", ""),
                body=comment_data.get("body", ""),
                score=comment_data.get("score", 0),
                created_utc=comment_data.get("created_utc", 0),
                permalink=f"{self.base_url}{comment_data.get('permalink', '')}"
            )
            comments.append(comment)
            
            # Recursively extract replies
            if "replies" in comment_data and comment_data["replies"]:
                self._extract_comments(
                    comment_data["replies"],
                    comments,
                    max_results,
                    depth + 1
                )
    
    def find_relevant_subreddits(self, query: str, max_results: int = 10) -> List[Dict]:
        """Find subreddits relevant to the query.
        
        Args:
            query: Search query
            max_results: Maximum number of subreddits to return
            
        Returns:
            List of subreddit information dictionaries
        """
        self._rate_limit()
        
        url = f"{self.base_url}/subreddits/search.json"
        
        params = {
            "q": query,
            "limit": min(max_results, 25),
            "raw_json": 1
        }
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                subreddits = []
                
                for child in data.get("data", {}).get("children", []):
                    sub_data = child.get("data", {})
                    
                    subreddit = {
                        "name": sub_data.get("display_name", ""),
                        "title": sub_data.get("title", ""),
                        "description": sub_data.get("public_description", ""),
                        "subscribers": sub_data.get("subscribers", 0),
                        "url": f"{self.base_url}/r/{sub_data.get('display_name', '')}"
                    }
                    subreddits.append(subreddit)
                
                return subreddits[:max_results]
            else:
                return []
        
        except requests.RequestException:
            return []
    
    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        
        self.last_request_time = time.time()
