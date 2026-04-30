"""Technical vocabulary for formality scoring."""
from __future__ import annotations

_TECHNICAL_WORDS = (
    "algorithm api argument array async authentication authorization backend bandwidth binary "
    "boolean bug cache callback class cli client compiler concurrency config configuration "
    "container context coroutine cryptography daemon database dataframe debug decimal decorator "
    "dependency deployment dictionary docker domain endpoint exception executable filesystem "
    "firewall framework frontend function garbage gateway generator git github graphql hash "
    "header heap http https immutable index inference infrastructure integer integration "
    "interface interpreter iteration json jwt kernel kubernetes lambda latency library linux "
    "load localhost log loop machine markdown matrix memory middleware migration model module "
    "namespace nginx node nullable object operator optimization orchestrator package packet "
    "parameter parser partition pipeline pixel plugin pointer port postfix postgresql predicate "
    "prefix procedure process protocol proxy query queue radix reactive recursive redis refactor "
    "regex registry repository request response rest router runtime schema script sdk serializer "
    "server service session sha256 shell signature snapshot socket sql sqlite ssh ssl stack state "
    "statement stream string subnet subroutine swagger syntax systemd table tcp template tensor "
    "terminal thread token tokenizer transaction transformer tuple typescript udp unicode unit unix "  # noqa: E501
    "url user utf uuid variable vector version virtual vlan vm vpn websocket worker xml yaml "
    "accuracy activation backpropagation batch bayesian bias bootstrap centroid classification "
    "cluster coefficient confidence convolution correlation covariance dataset derivative dimension "  # noqa: E501
    "distribution eigenvalue embedding entropy epoch estimator feature gradient histogram "
    "hyperparameter kmeans likelihood linear logistic loss mean median metric neural normalization "
    "null outlier overfitting perceptron precision probability quantile recall regression "
    "regularization sample scalar sigmoid stochastic supervised training validation variance weight "  # noqa: E501
    "asymptotic axiom calculus complex convergence cosine determinant differential eigenvector "
    "exponential fourier integral jacobian laplace logarithm modulus partial polynomial quaternion "
    "sinusoid theorem transform trigonometry benchmark compliance deterministic efficiency "
    "encapsulation equivalence idempotency implementation invariant modularity observability "
    "overhead parallelism redundancy scalability serialization synchronization throughput tolerance "  # noqa: E501
    "topology transactional transparency workload"
)
TECHNICAL_VOCABULARY = frozenset(_TECHNICAL_WORDS.split())
