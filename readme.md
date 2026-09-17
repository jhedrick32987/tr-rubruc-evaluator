# DC Summit 2026 Global Government Workshop — Team Repository

Welcome! This is your team's Git repository for the DC Summit 2026 Global Government Workshop. Use it to build, collaborate on, and submit your workshop project.

## How This Repository Works

This repository is hosted on [AWS CodeCommit](https://aws.amazon.com/codecommit/) in your team's AWS account. It was automatically provisioned when your environment was set up, and is **already cloned** to your DCV desktop at:

```
C:\Users\participant\workshop
```

Kiro opens this folder by default when you launch it.

### Connection to CodeCommit

The repository authenticates via [git-remote-codecommit](https://docs.aws.amazon.com/codecommit/latest/userguide/setting-up-git-remote-codecommit.html), which uses your instance's AWS credentials — **no additional Git credential setup is required**. You can push and pull using standard Git commands immediately.

The CodeCommit HTTPS clone URL is also available in the Workshop Studio **Event Outputs** panel (look for `CodeCommitUrl`) if you need to clone the repo elsewhere.

## Getting Started

Open **PowerShell** or the **Kiro terminal** and start building:

```powershell
cd C:\Users\participant\workshop

# Check current status
git status

# Create a branch for your feature
git checkout -b feature/my-awesome-idea

# Make changes, then stage and commit
git add .
git commit -m "Initial project structure"

# Push to CodeCommit
git push origin feature/my-awesome-idea
```

### Suggested Workflow

1. **Create a feature branch** — Keep `main` clean; do your work on feature branches.
2. **Commit often** — Small, frequent commits make it easier to track progress and recover from mistakes.
3. **Push regularly** — Your code is only saved to CodeCommit when you push. Don't lose work!
4. **Merge to main** when your feature is ready:
   ```powershell
   git checkout main
   git merge feature/my-awesome-idea
   git push origin main
   ```

## Tools Available on Your Desktop

Your DCV instance comes pre-loaded with everything you need:

| Tool | Purpose |
|------|---------|
| **Kiro** | AI-powered IDE — spec-driven development, autopilot, hooks |
| **Amazon Quick** | AI work assistant — research, apps, flows, documentation |
| **AWS CLI v2** | Interact with AWS services from the command line |
| **AWS CDK** | Infrastructure as code (TypeScript, Python, Java, .NET, Go) |
| **Python 3.12+** | Python runtime with pip |
| **Node.js 22 + npm** | JavaScript/TypeScript runtime |
| **Java 17 & 21 (Corretto)** | Java runtime with Maven |
| **Go** | Go programming language |
| **.NET 8 SDK** | .NET runtime and SDK |
| **Docker Desktop** | Container runtime |
| **Git** | Version control (this repo!) |

## AWS Services

Your account includes access to a broad set of AWS services. Highlights:

- **Amazon Bedrock** — Foundation models (Claude Sonnet 4.6 & Haiku 4.5, Nova Pro/Lite/Micro, Titan Embeddings, and more), Agents, Knowledge Bases, AgentCore
- **AWS Lambda** — Serverless compute
- **Amazon ECS / EKS** — Container orchestration
- **Amazon S3 / DynamoDB** — Storage and databases
- **AWS Step Functions** — Workflow orchestration
- **Amazon SageMaker** — ML notebook instances

See the workshop guide for the full list of available services and permissions.

## Need Help?

- **Workshop guide**: Available at the Workshop Studio URL provided by your facilitator
- **AWS credentials expired?** Go to Workshop Studio → *Get AWS CLI credentials* and set fresh ones in PowerShell
- **Git issues?** Make sure your AWS environment variables are set (credentials are needed for `git-remote-codecommit`)

---

Good luck and happy building! 🚀

---

## For Workshop Developers / Facilitators

> This section documents how this repository's contents are packaged and deployed into participant CodeCommit repositories. Participants can ignore this.

### How CodeCommit Gets Populated

The contents of the `code/workshop/` directory in the workshop source repository are:

1. **Zipped** into `assets/project.zip`
2. **Uploaded to S3** (either Workshop Studio's managed bucket or a test bucket)
3. **Loaded into CodeCommit** by the CloudFormation template (`static/cloudformation/codecommit.yaml`) which references the S3 bucket/key for initial repository content

### Regenerating the Zip

After making changes to `code/workshop/`, regenerate the asset zip with:

```bash
# Package assets locally (without uploading to S3)
bash scripts/update-assets.sh --no-sync

# Package and upload to Workshop Studio's S3 bucket
bash scripts/update-assets.sh

# Dry run — see what would happen without doing anything
bash scripts/update-assets.sh --dry-run
```

This runs the `update-assets.sh` script which zips `code/workshop/` → `assets/project.zip` and syncs the `assets/` directory to S3.

> **Important:** After uploading via Workshop Studio, the assets are only available once a **commit is pushed** to the workshop repository.

### For Standalone / Isengard Testing

If you're testing outside Workshop Studio (e.g., in an Isengard account), use the standalone upload script instead:

```bash
# Creates a private S3 bucket and uploads assets
bash scripts/update-assets.sh --standalone

# Use an existing bucket
bash scripts/update-assets.sh --standalone --bucket my-bucket

# Clean up
bash scripts/update-assets.sh --standalone --delete
```

Then deploy the CloudFormation stack with:
```bash
aws cloudformation deploy \
  --template-file static/cloudformation/codecommit.yaml \
  --stack-name workshop-codecommit \
  --parameter-overrides \
    S3CodeBucket=<bucket-name> \
    S3CodeKey=<prefix>/project.zip
```
