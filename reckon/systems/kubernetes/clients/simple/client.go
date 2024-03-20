/*
Copyright 2016 The Kubernetes Authors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

// Note: the example only works with the code within the same release/branch.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"

	appsv1 "k8s.io/api/apps/v1"
	apiv1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	v1 "k8s.io/client-go/kubernetes/typed/apps/v1"
	corev1 "k8s.io/client-go/kubernetes/typed/core/v1"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/util/flowcontrol"
	"k8s.io/client-go/util/retry"

	rc_go "github.com/Cjen1/reckon/reckon/goclient"
	rc_types "github.com/Cjen1/reckon/reckon/goclient/types"
)

type rc_k8s_cli struct {
	Core   corev1.CoreV1Interface
	App    v1.AppsV1Interface
	Client v1.DeploymentInterface
}

type UpdateData struct {
	ReplicaDelta int32 `json:"replicaDelta"`
}

// Creates a deployment on a K8s cluster
// The function uses the creaion key as deployment name, and value as the (absolute) path of the deployment YAML file to load.
// It then loads the file, deploys it to the configured cluster and returns (optionally with errors in case anything bad happened)
func (c rc_k8s_cli) Create(k string, v string) (string, error) {
	// Read the supplied deployment file
	b, err := os.ReadFile(v)
	if err != nil {
		return "", err
	}
	var deployment *appsv1.Deployment
	err = json.Unmarshal(b, &deployment)
	if err != nil {
		return "", err
	}
	// Rename the deployment
	deployment.SetName(k)
	//deployment.SetNamespace(k)
	labels := deployment.GetLabels()
	labels["app"] = k
	deployment.SetLabels(labels)
	deployment.Spec.Selector.MatchLabels["app"] = k
	deployment.Spec.Template.ObjectMeta.Labels["app"] = k
	deployment.Spec.Template.Spec.TopologySpreadConstraints[0].LabelSelector.MatchLabels["app"] = k

	// Create Deployment
	result, err := c.Client.Create(context.TODO(), deployment, metav1.CreateOptions{})
	return result.GetName(), err
}

// Retrieves pods part of a deployment
// The function uses the read key as deployment name
func (c rc_k8s_cli) Read(k string) (string, string, error) {
	list, err := c.Core.Pods("").List(context.TODO(), metav1.ListOptions{LabelSelector: fmt.Sprintf("app=%s", k)})
	if err != nil {
		return "", "", err
	}
	res, err := json.Marshal(list.Items)
	return "", string(res), err
}

// Updates a deployment on a K8s cluster
// The function uses the update key as deployment name, and value as a JSON object with the modifications to be applied to the deployment
func (c rc_k8s_cli) Update(k string, v string) (string, error) {
	// Unmarshal the JSON
	var data *UpdateData
	err := json.Unmarshal([]byte(v), &data)
	if err != nil {
		return "", err
	}

	retryErr := retry.RetryOnConflict(retry.DefaultRetry, func() error {
		// Retrieve the latest version of Deployment before attempting update
		// RetryOnConflict uses exponential backoff to avoid exhausting the apiserver
		result, getErr := c.Client.Get(context.TODO(), k, metav1.GetOptions{})
		if getErr != nil {
			fmt.Println(fmt.Errorf("failed to get latest version of Deployment: %v", getErr))
			return getErr
		}

		result.Spec.Replicas = int32Ptr(data.ReplicaDelta) // update replica count
		//result.Spec.Template.Spec.Containers[0].Image = "nginx:1.13" // change nginx version
		_, updateErr := c.Client.Update(context.TODO(), result, metav1.UpdateOptions{})
		return updateErr
	})
	if retryErr != nil {
		return "", retryErr
	}
	return k, nil
}

// Deletes the K8s deployment with name k
func (c rc_k8s_cli) Delete(k string) (string, error) {
	deletePolicy := metav1.DeletePropagationForeground
	err := c.Client.Delete(context.TODO(), k, metav1.DeleteOptions{
		PropagationPolicy: &deletePolicy,
	})
	return "", err
}

func (c rc_k8s_cli) Close() {
	// Do nothing - K8s clients apparently don't need to be closed manually...
}

func main() {
	log.Print("Client: Starting client memory client")
	f_client_id := flag.String("id", "-1", "Client id")
	f_new_client_per_request := flag.Bool("ncpr", false, "New client per request")
	kubeconfig := flag.String("kubeconfig", "", "absolute path to the kubeconfig file")

	flag.Parse()

	// Configure the Kubernetes client
	gen_cli := func() (rc_types.AbstractClient, error) {
		config, err := clientcmd.BuildConfigFromFlags("", *kubeconfig)
		if err != nil {
			fmt.Println("Error when building config")
			return nil, err
		}
		config.RateLimiter = flowcontrol.NewTokenBucketRateLimiter(50, 250)
		clientset, err := kubernetes.NewForConfig(config)
		if err != nil {
			fmt.Println("Error when creating clientset")
			return nil, err
		}

		app := clientset.AppsV1()
		core := clientset.CoreV1()
		deploymentsClient := app.Deployments(apiv1.NamespaceDefault)
		return rc_k8s_cli{App: app, Core: core, Client: deploymentsClient}, nil
	}

	rc_cli := rc_go.RC_CRUD_Client{}
	rc_cli.Run(gen_cli, *f_client_id, *f_new_client_per_request)
}

/*
func TestClient_Interactive(gen_cli func() (rc_types.AbstractClient, error)) {
	// Test create deployment
	cli, err := gen_cli()
	k8s_cli := cli.(rc_k8s_cli)
	if err != nil {
		panic(err)
	}

	res, err := k8s_cli.Create("test-deployment", "/root/reckon/systems/kubernetes/testdep.json")
	if err != nil {
		fmt.Println("Error when creating the deployment")
		panic(err)
	}
	fmt.Println("Create result: %s", res)
	prompt()
	// Test Read
	_, res, err = k8s_cli.Read("test-deployment")
	if err != nil {
		panic(err)
	}
	fmt.Println("Read of test-deployment result: %s", res)
	prompt()
	_, res, err = k8s_cli.Read("this-dep-does-not-exist")
	if err != nil {
		panic(err)
	}
	fmt.Println("Read of this-dep-does-not-exist result: %s", res)
	prompt()
	// Test Update
	res, err = k8s_cli.Update("test-deployment", `{"replicaDelta":-1}`)
	if err != nil {
		panic(err)
	}
	fmt.Println("Update of test-deployment by -1 replicas result: %s", res)
	prompt()
	_, res, err = k8s_cli.Read("test-deployment")
	if err != nil {
		panic(err)
	}
	fmt.Println("Read of test-deployment result: %s", res)
	prompt()
	// Test delete
	res, err = k8s_cli.Delete("test-deployment")
	if err != nil {
		panic(err)
	}
	fmt.Println("Delete of test-deployment result: %s", res)
	prompt()
}

func prompt() {
	fmt.Printf("-> Press Return key to continue.")
	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		break
	}
	if err := scanner.Err(); err != nil {
		panic(err)
	}
	fmt.Println()
}
*/

func int32Ptr(i int32) *int32 {
	return &i
}
