"""Train and print the integer controller. python -m residual_zero.qa"""

from residual_zero.qa.train import train


def main() -> None:
    model = train()
    print(f"n_credits {model.n_credits}")
    print(f"n_docs {model.n_docs}")
    print(f"n_labels {model.n_labels}")
    print(f"n_train {model.n_train}")
    print(f"holdout {model.n_holdout_ok}/{model.n_holdout}")
    print("writes_cleared 0")


if __name__ == "__main__":
    main()
