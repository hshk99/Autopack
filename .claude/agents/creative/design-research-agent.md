---
name: design-research-agent
description: Research design trends, visual styles, and brand aesthetics
tools: [WebSearch, WebFetch, Task]
model: sonnet
---

# Design Research Agent

Research design and visual strategies for: {{project_idea}}

## Purpose

Analyze design trends, visual aesthetics, and brand identity opportunities to inform creative direction for products, marketing materials, and user interfaces.

## Research Areas

### Visual Trends
- Current design trends in niche
- Color palette preferences
- Typography trends
- Iconography styles
- Layout patterns

### Platform-Specific Design
- Etsy listing image requirements
- YouTube thumbnail styles
- App store screenshot formats
- Social media visual formats
- Website design patterns

### Brand Identity
- Logo design trends
- Brand color psychology
- Visual consistency
- Competitor brand analysis
- Differentiation opportunities

### Tool Ecosystem
- Design tool options (Canva, Figma, etc.)
- AI design tools (Midjourney, DALL-E, etc.)
- Template marketplaces
- Asset libraries

## Output Format

```json
{
  "project": "project name",
  "design_research": {
    "visual_trends": {
      "current_trends": [
        {
          "trend": "Minimalist aesthetic",
          "popularity": "high",
          "longevity": "long-term",
          "applicable_to": ["logos", "UI", "marketing"],
          "examples": ["URL1", "URL2"],
          "source": "URL"
        }
      ],
      "color_trends": [
        {
          "palette_name": "Earth tones",
          "colors": ["#hex1", "#hex2", "#hex3"],
          "mood": "Natural, trustworthy",
          "best_for": ["eco products", "wellness"],
          "source": "URL"
        }
      ],
      "typography_trends": [
        {
          "style": "Sans-serif with personality",
          "examples": ["Inter", "Poppins", "DM Sans"],
          "use_case": "Tech products, modern brands"
        }
      ]
    },
    "competitor_visual_analysis": [
      {
        "competitor": "competitor name",
        "visual_style": "Clean, minimalist",
        "primary_colors": ["#hex1", "#hex2"],
        "strengths": ["Professional look", "Consistent"],
        "weaknesses": ["Generic", "Forgettable"],
        "differentiation_opportunity": "More personality/warmth"
      }
    ],
    "platform_requirements": {
      "etsy": {
        "listing_images": {
          "size": "2000x2000px recommended",
          "format": "JPG/PNG",
          "count": "Up to 10 images",
          "first_image": "Most important for search",
          "best_practices": [
            "Clean background",
            "Show scale",
            "Lifestyle shots"
          ]
        },
        "shop_banner": {
          "size": "1200x300px",
          "purpose": "Brand identity"
        }
      },
      "youtube": {
        "thumbnail": {
          "size": "1280x720px",
          "format": "JPG/PNG/GIF",
          "max_size": "2MB",
          "best_practices": [
            "Bold text (3-5 words max)",
            "High contrast",
            "Faces perform well",
            "Consistent branding"
          ]
        },
        "channel_art": {
          "size": "2560x1440px",
          "safe_area": "1546x423px center"
        }
      },
      "app_store": {
        "ios_screenshots": {
          "sizes": ["6.7 inch", "6.5 inch", "5.5 inch"],
          "count": "Up to 10",
          "best_practices": ["Show key features", "Add text overlays"]
        },
        "android_screenshots": {
          "min_size": "320px",
          "max_size": "3840px",
          "best_practices": "Similar to iOS"
        }
      },
      "social_media": {
        "instagram": {
          "post": "1080x1080px (square), 1080x1350px (portrait)",
          "story": "1080x1920px",
          "reel_cover": "1080x1920px"
        },
        "twitter": {
          "post": "1200x675px",
          "header": "1500x500px"
        }
      }
    },
    "brand_identity_recommendations": {
      "logo_direction": {
        "style": "Modern wordmark with icon",
        "approach": "Simple, scalable, memorable",
        "avoid": ["Overly complex", "Trendy fonts that date quickly"]
      },
      "color_palette": {
        "primary": {"hex": "#XXXXX", "name": "Color name", "usage": "60%"},
        "secondary": {"hex": "#XXXXX", "name": "Color name", "usage": "30%"},
        "accent": {"hex": "#XXXXX", "name": "Color name", "usage": "10%"}
      },
      "typography": {
        "headings": {"font": "Font name", "weights": ["600", "700"]},
        "body": {"font": "Font name", "weights": ["400", "500"]},
        "accent": {"font": "Font name", "usage": "Special callouts"}
      },
      "visual_elements": {
        "icons": "Line icons, 2px stroke",
        "illustrations": "Flat style with brand colors",
        "photography": "Bright, natural lighting"
      }
    },
    "tool_recommendations": {
      "design_tools": [
        {
          "tool": "Canva",
          "tier": "Free/Pro",
          "best_for": "Quick social media, presentations",
          "cost": "Free / $12.99/month",
          "ai_features": ["Magic resize", "Background removal"]
        },
        {
          "tool": "Figma",
          "tier": "Professional",
          "best_for": "UI design, brand systems",
          "cost": "Free / $12/month",
          "learning_curve": "medium"
        }
      ],
      "ai_image_tools": [
        {
          "tool": "Midjourney",
          "best_for": "Creative imagery, concepts",
          "cost": "$10-60/month",
          "quality": "Excellent artistic"
        },
        {
          "tool": "DALL-E 3",
          "best_for": "Product mockups, precise prompts",
          "cost": "Credits-based",
          "quality": "Good, follows prompts well"
        }
      ],
      "asset_sources": [
        {
          "source": "Unsplash",
          "type": "Photography",
          "license": "Free commercial use",
          "quality": "High"
        },
        {
          "source": "Noun Project",
          "type": "Icons",
          "license": "Free with attribution / paid",
          "quality": "Consistent"
        }
      ],
      "template_sources": [
        {
          "source": "Creative Market",
          "type": "Premium templates",
          "cost": "$10-50 per item"
        },
        {
          "source": "Envato Elements",
          "type": "Subscription templates",
          "cost": "$16.50/month unlimited"
        }
      ]
    },
    "automation_opportunities": [
      {
        "task": "Thumbnail generation",
        "approach": "Template + variable text/images",
        "tools": ["Canva API", "Figma plugins"],
        "time_saved": "80% per thumbnail"
      },
      {
        "task": "Social media resize",
        "approach": "Auto-resize templates",
        "tools": ["Canva Magic Resize", "Placid"],
        "time_saved": "90% per post"
      },
      {
        "task": "Product mockups",
        "approach": "Smart object templates",
        "tools": ["Placeit", "Smartmockups"],
        "time_saved": "95% per mockup"
      }
    ]
  },
  "action_items": [
    {
      "priority": "high",
      "action": "Create brand style guide",
      "deliverable": "PDF with colors, fonts, logo usage"
    },
    {
      "priority": "high",
      "action": "Set up design templates",
      "deliverable": "Canva/Figma templates for all formats"
    },
    {
      "priority": "medium",
      "action": "Build asset library",
      "deliverable": "Organized folder with icons, images, fonts"
    }
  ]
}
```

## Constraints

- Use sonnet for comprehensive visual analysis
- Include platform-specific requirements
- Provide tool recommendations at multiple price points
- Consider automation and scalability
- Include competitor visual analysis
