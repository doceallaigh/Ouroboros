#!/bin/bash
# Long-running AI development task
# Demonstrates multi-agent collaboration on building a machine learning system

cd "$(dirname "$0")"

python3 << 'PYTHON_SCRIPT'
import sys
sys.path.insert(0, 'src')

from main import CentralCoordinator
from filesystem import FileSystem

# Initialize the system
filesystem = FileSystem(working_dir="workspace")
coordinator = CentralCoordinator("src/roles.json", filesystem, replay_mode=False)

# This is a complex, long-running request that will require:
# 1. Multiple developer tasks (building ML components)
# 2. Data preparation and processing
# 3. Model training (the time-intensive part)
# 4. Auditor review of the implementation
# 5. Testing and validation

user_request = """
Create a complete machine learning project that builds and trains a sentiment analysis model:

REQUIREMENTS:
1. Create a requirements.txt with necessary ML libraries (numpy, scikit-learn, pandas, datasets)
2. Build a data preprocessing module that:
   - Downloads a sentiment dataset (you can use a small one from HuggingFace)
   - Performs text cleaning and normalization
   - Creates train/test splits
   - Vectorizes text using TF-IDF
   
3. Implement a sentiment classifier that:
   - Uses a Naive Bayes or SVM classifier from scikit-learn
   - Trains on the preprocessed data
   - Saves the trained model to disk
   - Provides prediction capabilities
   
4. Create a comprehensive test suite that:
   - Tests the preprocessing pipeline
   - Validates the model accuracy
   - Tests prediction on sample texts
   
5. Build a training script that:
   - Downloads and prepares data (this will take time)
   - Trains the model on the dataset
   - Generates a performance report with accuracy, precision, recall, F1
   - Saves visualizations of the results

CONSTRAINTS:
- Use only open-source libraries
- Make the code production-ready with error handling
- Include comprehensive logging
- Document all functions and modules
- The data download and training should take significant time (10-30+ minutes)

DELIVERABLES:
- requirements.txt with all dependencies
- data_preprocessing.py module
- sentiment_classifier.py module  
- train_model.py script
- test_sentiment_model.py test suite
- README.md with usage instructions
- A trained model saved as sentiment_model.pkl
- Training report with performance metrics

This is a real machine learning project that will demonstrate the agents' ability to
collaborate on a complex, time-intensive task. The training process should take 15-30 minutes
depending on dataset size.
"""

print("=" * 80)
print("STARTING LONG-RUNNING COLLABORATIVE AI DEVELOPMENT TASK")
print("=" * 80)
print(f"\nTask: {user_request[:200]}...")
print("\nExpected runtime: 60-90+ minutes")
print("This task involves:")
print("  - Multiple developer tasks running in parallel")
print("  - Data downloading and preprocessing")
print("  - Model training (time-intensive)")
print("  - Comprehensive testing and auditing")
print("\n" + "=" * 80 + "\n")

try:
    results = coordinator.assign_and_execute(user_request)
    
    print("\n" + "=" * 80)
    print("TASK EXECUTION COMPLETED")
    print("=" * 80)
    print(f"\nGenerated {len(results)} results from agent collaboration:")
    for i, result in enumerate(results, 1):
        print(f"\n[Result {i}] Role: {result.get('role')}")
        print(f"  Status: {result.get('status')}")
        output = result.get('output', '')
        if len(output) > 500:
            print(f"  Output: {output[:500]}...[truncated]")
        else:
            print(f"  Output: {output}")
    
    print("\n" + "=" * 80)
    print("Check the 'workspace' directory for generated files and model artifacts")
    print("=" * 80)
    
except Exception as e:
    print(f"Error during execution: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

PYTHON_SCRIPT
