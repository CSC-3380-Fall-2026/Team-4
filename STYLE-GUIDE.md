# Git Master - Code Standards
PLEASE READ AND FOLLOW. PLEASEEEEEEEE 

## Style Guides & References
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [FastAPI Best Practices](https://github.com/zhanymkanov/fastapi-best-practices)

## File Organization Structure
- **`App/`**: Root directory for application code
  - **`templates/`**: Frontend templates and UI components
  - **`routers/`**: API endpoint definitions
  - **`models/`**: Database schemas and data models
  - **`app.py`**: Main runner for FastAPI

## Naming Conventions
- **Variables**: Lower `snake_case`, max two words, clear and descriptive.
- **Functions**: Lower `snake_case` with type hints, max two words.
- **Classes**: `PascalCase` (CamelCase).
- **Files**: Lower `snake_case`.

## Code Conventions
- **Max Nesting Depth**: Maximum 4 levels of indentation (fewer is better).
- **Comment and Docstring Policy**: All functions must have a docstring with a concise one-sentence description and variable details. Use `"""` for multi-line docstrings and `#` for inline comments or notes.
- **Function Creation**: Extract and split logic into smaller functions to keep code concise, readable, and independently testable.