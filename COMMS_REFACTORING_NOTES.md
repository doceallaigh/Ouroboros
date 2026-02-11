# Communications Refactoring - Design Notes

## Overview
Refactored `comms.py` to separate generic communication concerns from application-specific business logic using the Strategy pattern.

## Architecture

### Strategy Composition Flow

#### Output (Response) Processing
```
Raw API Response
    ↓
[1] Application-specific post-processing (optional)
    - LLMPostProcessor: removes <think> tags
    - Custom processors: domain-specific transforms
    ↓
[2] Default sanitization (always applied)
    - Type validation
    - Length truncation  
    - Null byte removal
    - Whitespace trimming
    ↓
Clean, Safe Output
```

#### Input (Message) Processing
```
Raw Message Dict
    ↓
[1] Default input sanitization (always applied)
    - Structure validation (dict with 'messages')
    - Message list validation (non-empty)
    - Field validation (role + content)
    - Content sanitization per message
    ↓
Validated Message
```

### Key Components

#### `OutputPostProcessingStrategy` (Protocol)
```python
class OutputPostProcessingStrategy(Protocol):
    def process(self, content: str) -> str:
        ...
```
Abstract interface for output processing strategies.

#### `InputPreProcessingStrategy` (Protocol)
```python
class InputPreProcessingStrategy(Protocol):
    def process(self, message: Dict[str, Any]) -> Dict[str, Any]:
        ...
```
Abstract interface for input processing strategies.

#### `DefaultOutputSanitizationStrategy` (comms.py)
Built-in strategy that **always** runs to guarantee output safety:
- Validates content is a string
- Truncates to max_length (default 50,000 chars)
- Removes null bytes and problematic characters
- Strips leading/trailing whitespace

**Responsibility:** Communication layer output safety guarantees

#### `DefaultInputSanitizationStrategy` (comms.py)
Built-in strategy that **always** runs to guarantee input validity:
- Validates message structure (dict with 'messages' field)
- Validates message list (non-empty, proper structure)
- Validates each message has 'role' and 'content'
- Sanitizes content in each message (max 10,000 chars)

**Responsibility:** Communication layer input validation guarantees

#### `LLMPostProcessor` (response_processing.py)
Application-specific strategy for LLM responses:
- Removes thinking tags (`<think>...</think>`)
- Can be extended for other LLM-specific transformations

**Responsibility:** Domain-specific business logic

### Usage Example

```python
from comms import extract_content_from_response, DefaultSanitizationStrategy
from response_processing import LLMPostProcessor

# With LLM post-processing
processor = LLMPostProcessor()
content = extract_content_from_response(response, post_processor=processor)
# Flow: Raw → Remove thinking tags → Sanitize → Clean output

# Without post-processing (still safe!)
content = extract_content_from_response(response)
# Flow: Raw → Sanitize → Clean output
```

### Benefits

1. **Separation of Concerns**
   - `comms.py`: Generic, reusable communication logic
   - `response_processing.py`: Application-specific transformations

2. **Composability**
   - Strategies can be chained
   - Easy to add new processing steps
   - No modification to comms layer needed

3. **Safety by Default**
   - `DefaultSanitizationStrategy` always runs
   - Communication layer guarantees safe output
   - Application can't accidentally skip sanitization

4. **Testability**
   - Each strategy tested independently
   - Mock strategies for unit tests
   - Clear boundaries between concerns

5. **Flexibility**
   - Applications inject their own processors
   - Can create custom strategies for different domains
   - No coupling to specific LLM behavior

## Testing

- **68 tests** for comms + response_processing
  - 8 tests for `DefaultOutputSanitizationStrategy`
  - 8 tests for `DefaultInputSanitizationStrategy`
  - Strategy composition and integration tests
- **114 tests total** including main.py integration
- Full coverage of strategy composition and edge cases

## Migration Notes

No breaking changes to existing code:
- `extract_content_from_response()` signature unchanged (optional parameter added)
- `sanitize_output()` function still exists for backward compatibility
- All existing tests pass without modification
