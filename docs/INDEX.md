# Ouroboros Documentation Index

This documentation is organized into four categories to clarify the intended audience and purpose.

## 📋 Structure Overview

```
docs/
├── human/              # For project managers, stakeholders, and general understanding
├── agents/             # For AI agents executing tasks within the system
├── development/        # For developers building and extending the system
├── reference/          # Technical specifications and architectural details
└── INDEX.md            # This file
```

---

## 👥 For Humans (Project Management & Overview)

**Location**: [`docs/human/`](human/)

These documents provide a high-level understanding for non-technical stakeholders and project managers:

- **Executive Summary** - High-level project overview, goals, and status
- **Quick Reference** - Common tasks and quick lookup guide
- **Running Guide** - How to start and operate the system
- **Status Report** - Current project status and progress

**Start here if**: You need to understand what the project does, its current status, or how to run it.

---

## 🤖 For Agents (Task Execution & Tools)

**Location**: [`docs/agents/`](agents/)

These documents are specifically designed for AI agents executing tasks within the system:

- **Agent Tools Guide** - Complete reference for all available tools, methods, signatures, and examples
- **Best Practices** - Recommended patterns and approaches for agent task execution
- **Tool Injection Summary** - How agent tools are made available at runtime

**Start here if**: You are an AI agent needing to understand what capabilities you have and how to use them.

---

## 🛠️ Development (System Architecture & Modification)

**Location**: [`docs/development/`](development/)

These documents are for developers extending or modifying the Ouroboros system:

- **Architecture Guide** - System design, component overview, and data flow
- **Refactoring Changes** - Recent refactoring work, patterns, and lessons learned
- **Verification Checklist** - Testing and validation procedures for changes
- **Change Log** - Detailed history of modifications and improvements

**Start here if**: You are developing features, fixing bugs, or extending the system.

---

## 📚 Reference (Technical Specifications)

**Location**: [`docs/reference/`](reference/)

These documents contain technical specifications and detailed implementation details:

- **Implementation Details** - Low-level technical specifications
- **Configuration Reference** - All configurable parameters and their meanings
- **API Documentation** - Function signatures, parameters, return values, and exceptions
- **Error Codes** - Complete error reference and troubleshooting

**Start here if**: You need technical specifications or are debugging specific issues.

---

## 🎯 Quick Navigation

### By Role

**I'm a Project Manager:**
→ Start with [`docs/human/EXECUTIVE_SUMMARY.md`](human/EXECUTIVE_SUMMARY.md)

**I'm an AI Agent:**
→ Start with [`docs/agents/AGENT_TOOLS_GUIDE.md`](agents/AGENT_TOOLS_GUIDE.md)

**I'm a Developer:**
→ Start with [`docs/development/ARCHITECTURE.md`](development/ARCHITECTURE.md)

**I'm Debugging an Issue:**
→ Check [`docs/reference/TROUBLESHOOTING.md`](reference/TROUBLESHOOTING.md)

### By Task

**How do I run the system?**
→ [`docs/human/RUNNING.md`](human/RUNNING.md)

**What tools can I use?**
→ [`docs/agents/AGENT_TOOLS_GUIDE.md`](agents/AGENT_TOOLS_GUIDE.md)

**How is the system structured?**
→ [`docs/development/ARCHITECTURE.md`](development/ARCHITECTURE.md)

**What changed recently?**
→ [`docs/development/CHANGE_LOG.md`](development/CHANGE_LOG.md)

---

## 📑 File Organization

### Root Level (Legacy - Being Migrated)

Some documentation files remain in the root directory during transition:
- `README.md` - Main entry point, links to this structure
- `STATUS.md` - Current status (being migrated to `docs/human/`)
- `DOCUMENTATION.md` - Documentation guide (being migrated to `docs/development/`)

### New Structure

All new and updated documentation follows this organizational scheme:

```
docs/
├── human/
│   ├── EXECUTIVE_SUMMARY.md      # Project overview for stakeholders
│   ├── QUICK_REFERENCE.md         # Quick lookup guide
│   ├── RUNNING.md                 # How to operate the system
│   └── STATUS.md                  # Current project status
│
├── agents/
│   ├── AGENT_TOOLS_GUIDE.md       # Complete tools reference for AI agents
│   ├── BEST_PRACTICES.md          # Recommended agent patterns
│   └── TOOL_INJECTION_SUMMARY.md  # Runtime tool availability
│
├── development/
│   ├── ARCHITECTURE.md            # System design and components
│   ├── REFACTORING_CHANGES.md     # Recent refactoring work
│   ├── VERIFICATION_CHECKLIST.md  # Testing procedures
│   └── CHANGE_LOG.md              # Detailed modification history
│
├── reference/
│   ├── TROUBLESHOOTING.md         # Error codes and solutions
│   ├── CONFIGURATION_REFERENCE.md # Configurable parameters
│   └── API_DOCUMENTATION.md       # Function signatures and specs
│
└── INDEX.md                        # This navigation guide
```

---

## 🔄 Migration Status

**Phase 1 (Current)**: Structure created, index established
- ✅ Directory structure created
- ⏳ Documents being organized and moved
- ⏳ Cross-references being updated

**Phase 2 (Next)**: Reorganize existing documents
- Move human-facing docs to `docs/human/`
- Move agent docs to `docs/agents/`
- Move technical docs to `docs/development/`
- Create missing reference materials

---

## 📖 How to Use This Documentation

1. **Find your role** above in "By Role" section
2. **Start with recommended document** for your role
3. **Use the table of contents** to navigate to specific topics
4. **Cross-references** link to related documents in other categories
5. **Return to this index** if you need to switch focus

---

## 🤝 Contributing to Documentation

When adding new documentation:

1. **Determine the audience**: Human, Agent, Developer, or Reference?
2. **Place in appropriate directory**: `docs/{category}/`
3. **Follow naming convention**: `DOCUMENT_NAME.md` (uppercase, underscores)
4. **Update this index**: Add cross-references and update the file organization section
5. **Update category README**: Each category should have a local index

---

## ❓ Still Looking for Something?

- Check the **README.md** at the root for general project information
- Look in **STATUS.md** for current project status
- Browse the **DOCUMENTATION.md** for implementation details
- Use filesystem search to find specific topics

---

**Last Updated**: February 8, 2026  
**Structure Version**: 1.0
